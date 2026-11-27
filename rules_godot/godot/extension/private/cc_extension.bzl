"""
godot_cc_extension: the C++ shorthand of godot_extension, and the private targets it
generates: the cc_library of the extension's code and the shared library linked from it.
"""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//godot/private:macros.bzl", "CALLER_PACKAGE")
load(":extension.bzl", "source_extension", "tool_view_of")
load(":ios_framework.bzl", "ios_framework")

visibility(["//godot/extension"])

# Attributes every rule has, which godot_cc_extension passes to its shared library too.
_RULE_ATTRS = ["compatible_with", "deprecation", "exec_compatible_with", "exec_properties", "features", "restricted_to", "toolchains"]

# Attributes of the link alone; the cc_library has its own linkstatic.
_LINK_ATTRS = ["linkstatic"]

def _native_archive(name, srcs, hdrs, deps, entry_symbol, tags, kwargs):
    """Declare the cc_library of the extension's C++ code, which iOS links into the application."""
    archive_kwargs = {key: value for key, value in kwargs.items() if key not in _LINK_ATTRS}

    # iOS links the archive into the application, which keeps and exports the entry symbol.
    archive_kwargs["linkopts"] = archive_kwargs.get("linkopts", []) + select({
        Label("@platforms//os:ios"): [
            "-Wl,-u,_" + entry_symbol,
            "-Wl,-exported_symbol,_" + entry_symbol,
        ],
        "//conditions:default": [],
    })
    cc_library(
        name = name,
        srcs = srcs,
        hdrs = hdrs,
        deps = deps,
        alwayslink = True,
        linkstatic = True,
        visibility = CALLER_PACKAGE,
        # The extension builds it in its own configuration, without --strip.
        tags = tags + ["manual"],
        **archive_kwargs
    )

def _generated_attrs(attrs):
    """The attributes of a private target godot_cc_extension generates from its own attrs."""
    return {key: attrs[key] for key in ["testonly", "target_compatible_with"] if key in attrs} | {
        "visibility": CALLER_PACKAGE,
        "tags": attrs["tags"] + ["manual"],
    }

def _shared_library(name, archive, entry_symbol, attrs):
    """
    Declare the shared library of extension name linked from archive.

    On iOS the framework's binary combines it across the application's CPUs.

    Args:
        name: The extension's target name.
        archive: Name of the extension's cc_library in this package.
        entry_symbol: The extension's entry symbol, the only one the library exports.
        attrs: The attributes godot_cc_extension received: its kwargs and its tags.

    Returns:
        The name of the shared library target.
    """

    # A cc_binary names its output after the target. The part after the slash keeps the
    # delivered file lib<name>_native.so, while the target stays in the macro's namespace.
    shared = name + ".shared/lib" + name + "_native.so"

    # The shared library also takes the attributes common to all rules and the link's own.
    generated = _generated_attrs(attrs)
    binary_kwargs = generated | {
        key: attrs[key]
        for key in _LINK_ATTRS + _RULE_ATTRS
        if key in attrs
    }

    # The library exports only its entry symbol, as godot-cpp's own build does. Each
    # extension links its own godot-cpp, and an exported copy would be shared with the
    # other extensions in the process: dyld binds weak definitions across images.
    exports = name + ".exports"
    write_file(
        name = exports,
        out = exports + ".lds",
        content = ["{ global: %s; local: *; };" % entry_symbol],
        **generated
    )

    # The shared library links the archive and everything it links. Not cc_shared_library:
    # it links only the static libraries its aspect reaches through deps and drops others,
    # such as the Objective-C targets of rules_swift_package_manager behind their
    # minimum-OS transition. Shared dependencies load from beside the extension library,
    # where the extension places them, as vendors' libraries expect (@loader_path, $ORIGIN).
    apple_exports = ["-Wl,-exported_symbol,_" + entry_symbol]
    cc_binary(
        name = shared,
        deps = [":" + archive],
        linkshared = True,
        additional_linker_inputs = select({
            Label("@platforms//os:macos"): [],
            Label("@platforms//os:ios"): [],
            "//conditions:default": [":" + exports],
        }),
        linkopts = select({
            Label("@platforms//os:macos"): apple_exports + ["-Wl,-rpath,@loader_path"],
            # The binary of a framework in the application's Frameworks directory, beside
            # the frameworks it loads. The framework rewrites its install name, which
            # needs header room for a longer one.
            Label("@platforms//os:ios"): apple_exports + [
                "-Wl,-rpath,@executable_path/Frameworks",
                "-Wl,-rpath,@loader_path/..",
                "-Wl,-headerpad_max_install_names",
            ],
            "//conditions:default": [
                "-Wl,-rpath,$$ORIGIN",
                "-Wl,--version-script,$(execpath :%s)" % exports,
            ],
        }),
        **binary_kwargs
    )
    return shared

def _cc_extension_impl(
        name,
        visibility,
        srcs,
        entry_symbol,
        deps,
        hdrs,
        data,
        resource_path,
        compatibility_minimum,
        reloadable,
        minimum_os_versions,
        tags,
        platform_deps,
        infoplists,
        ios_linkage,
        ios_bundle_id,
        **kwargs):
    # Unset attributes stay unset on the generated targets.
    kwargs = {key: value for key, value in kwargs.items() if value != None}
    tags = tags or []
    archive = name + ".native"
    _native_archive(archive, srcs, hdrs, deps, entry_symbol, tags, kwargs)
    attrs = kwargs | {"tags": tags}
    shared = _shared_library(name, archive, entry_symbol, attrs)
    ios_library = ios_framework(name, shared, ios_bundle_id, _generated_attrs(attrs)) if ios_linkage == "framework" else archive
    library = select({
        Label("@platforms//os:ios"): ":" + ios_library,
        "//conditions:default": ":" + shared,
    })
    source_extension(
        name = name,
        minimum_os_versions = minimum_os_versions,
        implementation_deps = select({
            Label("@platforms//os:ios"): [":" + archive],
            "//conditions:default": [],
        }),
        deps = platform_deps,
        infoplists = infoplists,
        visibility = visibility,
        target_compatible_with = kwargs.get("target_compatible_with"),
        **tool_view_of(name, dict(
            library = library,
            data = data,
            entry_symbol = entry_symbol,
            resource_path = resource_path,
            compatibility_minimum = compatibility_minimum,
            reloadable = reloadable,
            tags = tags,
            testonly = kwargs.get("testonly"),
        ))
    )

godot_cc_extension = macro(
    doc = """
    Build C/C++ once as a cc_library, link it, and package it as a godot_extension.

    Every supported operating system takes a shared library linked from it that finds its
    shared dependencies beside it and exports only the entry symbol, so extensions in one
    process never run each other's godot-cpp. On iOS the shared library is the binary of a
    dynamic framework the application embeds and signs; with ios_linkage = "static", iOS
    takes the archive instead, which the application links, and the application's
    static extensions share one godot-cpp. Code linked by another rule, in any language,
    goes to godot_extension directly. godot_app links the extension and its C++
    dependencies when one of the packs it ships contains it. Like godot_extension, the
    target is an add-on of only that extension.

    Creates the named godot_extension target and the private targets `<name>.native`,
    the cc_library, `<name>.shared/lib<name>_native.so`, the shared library linked from
    it, which applications deliver as `lib<name>_native.so`, `<name>.ios_framework`, the
    framework import of iOS, and `<name>.tool`, the extension in the tool configuration
    that editor actions and the host editor load. The public target exposes
    GodotExtensionInfo, DefaultInfo and, on iOS, CcInfo. copts, defines, local_defines,
    includes and linkopts reach the cc_library; the attributes every rule has, such as
    features or exec_compatible_with, also reach the shared library, and linkstatic
    reaches only it. Compilation uses rules_cc toolchains. The feature tags of
    the libraries derive from the target platform's operating system and CPU, the iOS
    environment and the variant; features keeps its meaning as rules_cc toolchain
    features. An editor-specific backend is a select() over
    @autoload_rules_godot//godot:tool in deps.

    Example:
    ```starlark
    godot_cc_extension(
        name = "extension",
        srcs = ["extension.cpp"],
        deps = ["@godot_cpp//:godot_cpp"],
        entry_symbol = "my_extension_init",
    )
    ```

    See [a complete C++ extension](../../gdextension.md).
    """,
    implementation = _cc_extension_impl,
    inherit_attrs = "common",
    attrs = {
        "copts": attr.string_list(doc = "C/C++ compiler options of the extension's code, as cc_library's."),
        "defines": attr.string_list(
            doc = "Preprocessor definitions of the extension's code and its dependents, as cc_library's.",
        ),
        "local_defines": attr.string_list(
            doc = "Preprocessor definitions of the extension's code only, as cc_library's.",
        ),
        "includes": attr.string_list(doc = "Include directories of the extension's code, as cc_library's."),
        "linkopts": attr.string_list(doc = "Linker options of the extension's libraries, as cc_library's."),
        "linkstatic": attr.bool(
            doc = """
            Whether the shared library links its C++ dependencies statically, as cc_binary's;
            True by default, so the library needs no shared library of its dependencies.
            """,
            default = True,
        ),
        "srcs": attr.label_list(doc = "C/C++ source labels.", allow_files = True, mandatory = True),
        "entry_symbol": attr.string(
            doc = "Exported Godot entry function.",
            mandatory = True,
            configurable = False,
        ),
        "deps": attr.label_list(
            doc = """
            rules_cc dependencies; shared libraries among them are runtime dependencies
            placed beside the extension library, and iOS applications embed the dynamic
            frameworks they link, transitive ones included.
            """,
        ),
        "hdrs": attr.label_list(doc = "Private extension headers.", allow_files = True),
        "data": attr.label_list(
            doc = """
            Files the descriptor's [dependencies] lists beyond the libraries deps link, as
            godot_extension's data.
            """,
            allow_files = True,
        ),
        "resource_path": attr.string(
            doc = "Resource path of the descriptor; empty uses addons/<name>/<name>.gdextension.",
            configurable = False,
        ),
        "compatibility_minimum": attr.string(doc = "Oldest compatible Godot version.", default = "4.7.2"),
        "reloadable": attr.bool(doc = "Enable Godot editor reloading."),
        "minimum_os_versions": attr.string_dict(
            doc = """
            Minimum operating-system versions the extension libraries need, by Godot
            platform (macos, ios); a godot_app whose minimum is lower fails.
            """,
        ),
        "platform_deps": attr.label_list(
            doc = """
            Android or Apple platform libraries the extension's native code uses without
            linking them; godot_extension's platform_deps. Libraries it links belong to
            deps.
            """,
        ),
        "infoplists": attr.label_list(
            doc = "Info.plist fragments for the extension's native code; godot_extension's infoplists.",
            allow_files = True,
        ),
        "ios_linkage": attr.string(
            doc = """
            How iOS applications take the extension: "framework", the default, embeds a
            dynamic framework named after the extension, with its own godot-cpp; "static"
            links the archive into the executable, where all static extensions share one
            godot-cpp and its main loop callbacks.
            """,
            default = "framework",
            values = ["framework", "static"],
            configurable = False,
        ),
        "ios_bundle_id": attr.string(
            doc = "CFBundleIdentifier of the iOS framework; empty derives one from the extension's label.",
            configurable = False,
        ),
    },
)
