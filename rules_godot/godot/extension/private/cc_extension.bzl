"""
The private targets godot_cc_extension generates: the cc_library of the extension's code
and the shared library linked from it.
"""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")

visibility(["//godot/extension/..."])

# Attributes every rule has, which godot_cc_extension passes to its shared library too.
_RULE_ATTRS = ["compatible_with", "deprecation", "exec_compatible_with", "exec_properties", "features", "restricted_to", "toolchains"]

# Attributes of the link alone; the cc_library has its own linkstatic.
_LINK_ATTRS = ["dynamic_deps", "env", "link_extra_lib", "linkstatic", "malloc", "reexport_deps", "stamp"]

def native_archive(name, srcs, hdrs, deps, entry_symbol, tags, kwargs):
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
        visibility = ["//visibility:private"],
        # The extension builds it in its own configuration, without --strip.
        tags = tags + ["manual"],
        **archive_kwargs
    )

def generated_attrs(attrs):
    """The attributes of a private target godot_cc_extension generates from its own attrs."""
    return {key: attrs[key] for key in ["testonly", "target_compatible_with"] if key in attrs} | {
        "visibility": ["//visibility:private"],
        "tags": attrs["tags"] + ["manual"],
    }

def shared_library(name, archive, entry_symbol, attrs):
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

    # Native filename exception: Godot descriptors and existing packaged libraries
    # use lib<name>_native.so. Remove when rules_cc separates the label from the
    # shared-library filename without changing descriptor/resource identities.
    shared = "lib" + name + "_native.so"

    # The shared library also takes the attributes common to all rules and the link's own.
    generated = generated_attrs(attrs)
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
