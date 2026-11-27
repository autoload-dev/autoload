"""
Bzlmod setup of Godot engines, from their sources or prebuilt binaries, and of
experimental Android toolchains for each execution platform.

Sections: godot_engines, godot_android_toolchains.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_file")
load("//godot/engine/private:archives.bzl", "godot_editor_archive", "godot_export_templates_archive")
load("//godot/engine/private:extension_plan.bzl", "plan_engines")
load("//godot/engine/private:hub.bzl", "engine_hub", "engine_toolchains")
load(
    "//godot/engine/private:repositories.bzl",
    "godot_android_shell",
    "godot_engine_build",
    "godot_engine_source",
)
load(
    "//godot/platforms/private:android_toolchains.bzl",
    "android_toolchain_repositories",
    "plan_android_toolchains",
)

# ==== godot_engines ===========================================================

_ENGINE_REFERENCE_ATTR = attr.string(
    doc = "Name of the engine this tag completes, as its godot_engines.engine names it.",
    mandatory = True,
)

_ENGINE_ATTRS = {
    "name": attr.string(
        doc = """
        Name of the engine: targets select it with their `engine` attribute, such as
        `engine = "simulation"`. It also names the engine's hub repository, `@<name>`, which
        `register_toolchains("@<name>//toolchains:all")` registers, prefixes its other
        repositories and is the build name the engines built from source report in their
        version, such as 4.7.2.stable.simulation. Letters, digits and underscores, starting
        with a letter.
        """,
        mandatory = True,
    ),
    "version": attr.string(
        doc = """
        Exact canonical Godot version, such as 4.7.2 or 4.8.0-beta1. A catalogued version
        brings Godot's official sources and, without a build tag, its official editors,
        export templates and Android shell.
        """,
        mandatory = True,
    ),
    "default": attr.bool(doc = """
        Whether targets that name no engine take this one; it can still be named. The root
        module's default engine wins; a dependency's counts only when the root module names
        none, and at most one engine is the default.
        """),
    "lock_file": attr.label(doc = """
        Optional lock file that pins the build graph of every recipe built from source, such
        as `//engines/simulation:simulation.lock.json`. With it, no recipe is configured on
        this host; `bazel run @<name>//:pin` writes it, configuring each recipe on an
        execution platform Godot accepts, such as a remote Linux executor for Linux recipes.
        """),
}

_SOURCE_ATTRS = {
    "engine": _ENGINE_REFERENCE_ATTR,
    "urls": attr.string_list(doc = "Ordered mirror URLs of the same source archive.", mandatory = True),
    "sha256": attr.string(doc = "SHA-256 digest of the archive.", mandatory = True),
    "strip_prefix": attr.string(doc = "Top-level directory removed on extraction."),
    "version": attr.string(doc = """
        Canonical Godot version of the sources as their version.py names it, such as
        4.8.0-beta for the sources of 4.8.0-beta1; empty takes the engine's version.
        """),
}

_BINARIES_ATTRS = {
    "engine": _ENGINE_REFERENCE_ATTR,
    "editor_urls": attr.string_list_dict(
        doc = "Editor archive URLs by editor platform, such as linux_x86_64, linux_arm64, macos (universal), macos_arm64 or macos_x86_64; replaces the catalogue's editors.",
    ),
    "editor_integrity": attr.string_dict(
        doc = "Subresource Integrity digest per editor platform in editor_urls.",
    ),
    "editor_binaries": attr.string_dict(
        doc = "Editor executable path inside each archive; defaults to the official layout of a catalogued version.",
    ),
    "templates_urls": attr.string_list(
        doc = "Export-template archive URLs; replaces the catalogue's templates.",
    ),
    "templates_integrity": attr.string(
        doc = "Subresource Integrity digest of the templates in templates_urls.",
    ),
    "templates_macos_cpus": attr.string_list(
        doc = 'macOS layout of the templates in templates_urls: ["universal"] (default) or a subset of ["arm64", "x86_64"].',
    ),
    "templates_linux_cpus": attr.string_list(
        doc = "Linux template CPUs of the templates in templates_urls, as Godot's CPU tags; empty means those of Godot's official templates: arm32, arm64, x86_32 and x86_64.",
    ),
    "ios_simulator_cpus": attr.string_list(
        doc = "CPUs with usable code in the templates' iOS simulator XCFramework slice; replaces the catalogue's value. Empty for an uncatalogued version means no simulator runtimes.",
    ),
    "android_shell_urls": attr.string_list(
        doc = "Android shell AAR URLs, a template_release build with every ABI's engine library; replaces the catalogue's shell.",
    ),
    "android_shell_integrity": attr.string(
        doc = "Subresource Integrity digest of the AAR in android_shell_urls.",
    ),
    "android_debug_shell_urls": attr.string_list(
        doc = "Android shell AAR URLs of a template_debug build with every ABI's engine library; official releases publish none.",
    ),
    "android_debug_shell_integrity": attr.string(
        doc = "Subresource Integrity digest of the AAR in android_debug_shell_urls.",
    ),
}

_BUILD_ATTRS = {
    "engine": _ENGINE_REFERENCE_ATTR,
    "enabled_modules": attr.string_list(
        doc = "Enabled Godot modules and their default, as for godot_engine_build.",
    ),
    "default_modules": attr.bool(
        doc = "Also enable every module Godot enables by default for the platform, as its official builds do.",
    ),
    "custom_modules": attr.label_keyed_string_dict(
        doc = "Each custom module's config.py label mapped to its module name.",
        allow_files = [".py"],
    ),
    "patches": attr.label_list(
        doc = "Patch files applied in order to every recipe and the Android shell library.",
        allow_files = [".patch", ".diff"],
    ),
    "patch_strip": attr.int(doc = "Leading path components removed from patch filenames.", default = 1),
    "renderers": attr.string_list(
        doc = "Godot's rendering methods every recipe's engine runs, as for godot_engine_build.",
    ),
    "build_options": attr.string_dict(doc = "Upstream configure options, as for godot_engine_build."),
}

_EDITOR_ATTRS = {
    "engine": _ENGINE_REFERENCE_ATTR,
    "enabled_modules": attr.string_list(doc = """
        Enabled Godot modules of the engine's editors, which replace the build tag's
        enabled_modules and default_modules for them; empty keeps the build tag's.
        """),
    "default_modules": attr.bool(doc = """
        Also enable every module Godot enables by default in the engine's editors; with
        enabled_modules, it replaces the build tag's module selection for them.
        """),
    "build_options": attr.string_dict(doc = """
        Upstream configure options of the engine's editors, which replace the build tag's
        build_options for them, such as without its template-only options; empty keeps the
        build tag's.
        """),
}

_RUNTIME_PROFILE_ATTRS = {
    "profile": attr.label(
        doc = """
        A build profile (.gdbuild) whose build options applications' runtimes may apply,
        such as the one a godot_app's build_profile names.
        """,
        mandatory = True,
        allow_single_file = [".gdbuild"],
    ),
    "engine": attr.string(doc = """
        Name of the engine whose source recipes build the variant, as its
        godot_engines.engine names it; empty for the default engine.
        """),
}

_ENGINE_TAG_ATTRIBUTES = {
    "engine": _ENGINE_ATTRS.keys(),
    "source": _SOURCE_ATTRS.keys(),
    "binaries": _BINARIES_ATTRS.keys(),
    "build": _BUILD_ATTRS.keys(),
    "editor": _EDITOR_ATTRS.keys(),
}

# The repository rules and macros that plan_engines declarations name.
_ENGINE_RULES = {
    "engine_hub": engine_hub,
    "engine_toolchains": engine_toolchains,
    "godot_android_shell": godot_android_shell,
    "godot_editor_archive": godot_editor_archive,
    "godot_engine_build": godot_engine_build,
    "godot_engine_source": godot_engine_source,
    "godot_export_templates_archive": godot_export_templates_archive,
    "http_file": http_file,
}

def _engines_impl(module_ctx):
    def read(label):
        return module_ctx.read(module_ctx.path(label))

    for declaration in plan_engines(module_ctx.modules, tag_attributes = _ENGINE_TAG_ATTRIBUTES, read = read):
        _ENGINE_RULES[declaration.rule](**declaration.attrs)
    return module_ctx.extension_metadata(reproducible = True)

godot_engines = module_extension(
    doc = """
    Register Godot engines and generate their registration hubs.

    An engine is one `engine` tag, completed by the `source`, `binaries`, `build`, `editor`
    and `runtime_profile` tags that name it. What it can do follows from what it has:

    | Tags | Prebuilt binaries | Built from source |
    | --- | --- | --- |
    | `engine` of a catalogued version | Godot's official ones | the slots they lack, and every runtime of an application with a build profile or of an optimized release |
    | + `build` | none of the catalogue's | every slot |
    | + `binaries` | these, which match the engine's sources and build | as above, beside them; with pinned editors or templates, a fork's, only from a `source` tag's sources |
    | + `source` | as above | from these sources instead of the catalogue's |
    | `binaries` of an uncatalogued version, no `source` | these | none: build profiles fail analysis, and engine optimization leaves the binaries unchanged |

    Each engine's hub `@<name>` has one component per slot in its `toolchains` package:
    an editor per editor platform and a runtime per platform, CPU, iOS environment and
    variant. The extension also generates `@godot_engines_toolchains`, the toolchains of
    every engine's components, which rules_godot's own module registers: a module that
    registers an engine registers no toolchains itself. A root module's own registrations
    and `--extra_toolchains` come first; `@<name>//toolchains:all` registers one engine
    alone. Downloads and configuration happen only for payloads a build requests, so slots
    of platforms a build never targets cost nothing.

    Example (MODULE.bazel):
    ```starlark
    godot_engines = use_extension("@autoload_rules_godot//godot:extensions.bzl", "godot_engines")

    # Godot's official 4.7.2, which targets without an engine take.
    godot_engines.engine(name = "godot", version = "4.7.2", default = True)

    # The same release's sources with a module of the game's own.
    godot_engines.engine(
        name = "simulation",
        version = "4.7.2",
        lock_file = "//engines/simulation:simulation.lock.json",
    )
    godot_engines.build(
        engine = "simulation",
        custom_modules = {"//engines/simulation/modules/reaction_diffusion:config.py": "reaction_diffusion"},
        enabled_modules = ["gdscript", "text_server_fb", "reaction_diffusion"],
    )
    ```

    A module completes only the engines it registers. A root request owns its name;
    identical dependency requests share repositories and conflicting ones fail. See
    [engines](../../engine.md).
    """,
    implementation = _engines_impl,
    tag_classes = {
        "engine": tag_class(
            doc = """
            Register an engine by name and Godot version. A catalogued version needs no other
            tag: its official binaries and sources come with it.
            """,
            attrs = _ENGINE_ATTRS,
        ),
        "source": tag_class(
            doc = """
            Build an engine from these sources instead of the catalogue's, such as a fork's
            immutable archive. An uncatalogued version needs them to build from source.
            """,
            attrs = _SOURCE_ATTRS,
        ),
        "binaries": tag_class(
            doc = """
            Take an engine's prebuilt editors, export templates or Android shells from these
            pins, each replacing the catalogue's. Declaring them states that they match the
            engine's sources and build, such as a fork's release artifacts; slots they lack
            are built from source. Pinned editors or templates are a fork's, so only a source
            tag's sources build beside them, never the catalogue's.
            """,
            attrs = _BINARIES_ATTRS,
        ),
        "build": tag_class(
            doc = """
            Build an engine's recipes with this policy instead of the modules of Godot's
            official builds. The catalogue's binaries then no longer serve the engine: every
            slot its binaries tag does not pin is built from source.
            """,
            attrs = _BUILD_ATTRS,
        ),
        "editor": tag_class(
            doc = """
            Build an engine's editors with other modules or options than its runtimes, such
            as a fuller editor beside reduced runtimes. Patches and custom modules stay the
            build tag's.
            """,
            attrs = _EDITOR_ATTRS,
        ),
        "runtime_profile": tag_class(
            doc = """
            Register a build profile with build options for an engine's source-built
            runtimes. Its build options shape a recipe's graph, so every runtime recipe of
            the engine declares a runtime variant with them, beside its own graph, and with
            its own pin in a lock file; an application whose build_profile names the file
            gets that variant. A profile that only disables classes needs no registration,
            and an application whose profile sets build options without one fails with
            this tag's line.
            """,
            attrs = _RUNTIME_PROFILE_ATTRS,
        ),
    },
)

# ==== godot_android_toolchains ================================================

def _android_toolchains_impl(module_ctx):
    ndk_api_level = plan_android_toolchains(module_ctx.modules)
    if ndk_api_level != None:
        android_toolchain_repositories(name = "android_toolchains", ndk_api_level = ndk_api_level)
    return module_ctx.extension_metadata(reproducible = True)

godot_android_toolchains = module_extension(
    doc = """
    Register Android SDK and NDK toolchains for each execution platform. Experimental: the
    extension, its tag and its generated repository may change without notice.

    rules_android and rules_android_ndk resolve their tools from this host's SDK and NDK for
    every execution platform, so a remote Linux executor, such as BuildBuddy's, would run
    this host's `aapt2` and clang. This extension registers this host's NDK
    (`ANDROID_NDK_HOME`) for this host's operating system only, and SDK, Android and NDK
    toolchains for linux/x86_64 execution platforms: on hosts other than Linux, of the
    checksum-pinned Linux build tools 35.0.0, SDK platforms 35 and 36 and NDK r29, which
    Bazel downloads only when toolchain resolution selects them; on a Linux host, of this
    host's SDK and NDK. Actions on this host keep rules_android's toolchains of the host SDK
    (`ANDROID_HOME`). The Linux SDK follows `--@androidsdk//:api_level`; on hosts other than
    Linux, another API level fails analysis for Linux executors.

    The generated hub `android_toolchains` replaces `@androidndk//:all` of rules_android_ndk.
    Register it with `--extra_toolchains`, which gives it priority over the toolchains
    rules_android registers in its own module.

    Example (MODULE.bazel):
    ```starlark
    godot_android_toolchains = use_extension(
        "@autoload_rules_godot//godot:extensions.bzl",
        "godot_android_toolchains",
    )
    godot_android_toolchains.configure(ndk_api_level = 24)
    use_repo(godot_android_toolchains, "android_toolchains")
    ```

    Example (.bazelrc):
    ```
    build:android --extra_toolchains=@android_toolchains//:all
    ```

    The root module's tag applies; without one, the dependencies' tags must agree. See
    [remote execution of Android builds](../../platforms.md#remote-execution-of-android-builds).
    """,
    implementation = _android_toolchains_impl,
    tag_classes = {
        "configure": tag_class(
            doc = "Configure the NDK of the Android toolchains.",
            attrs = {
                "ndk_api_level": attr.int(
                    doc = """
                    Native API level the NDK compiles C++ for, the minimum Android version of
                    native code, such as 24. It applies to this host's NDK and the Linux NDK
                    alike, so local and remote compiles agree.
                    """,
                    mandatory = True,
                ),
            },
        ),
    },
)
