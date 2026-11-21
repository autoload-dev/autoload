"""
Bzlmod setup of Godot engines (prebuilt releases, sources and source builds) and of
experimental Android toolchains for each execution platform.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_file")
load(
    "//godot/engine:repositories.bzl",
    "godot_android_shell",
    "godot_editor_archive",
    "godot_engine_build",
    "godot_engine_source",
    "godot_engine_source_build",
    "godot_export_templates_archive",
)
load("//godot/engine/private:extension_plan.bzl", "plan_engines")
load("//godot/engine/private:hub.bzl", "engine_hub")
load(
    "//godot/platforms/private:android_toolchains.bzl",
    "android_toolchain_repositories",
    "plan_android_toolchains",
)

_ENGINE_ATTR = attr.string(doc = """
    Name of the engine the hub's components belong to, such as `petri`; builds select it
    with `--@autoload_rules_godot//godot:engine=petri`, and only then do these components fill
    slots. Empty, the default, joins the default engine.
    """)

_PREBUILT_ATTRS = {
    "name": attr.string(
        doc = "Hub repository name; editor and template repositories use it as prefix.",
        mandatory = True,
    ),
    "version": attr.string(
        doc = "Exact canonical Godot version, such as 4.7.2 or 4.8.0-beta1.",
        mandatory = True,
    ),
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
    "build_missing_runtimes": attr.bool(
        doc = """
            Build the runtime slots the prebuilt artifacts lack from the release's sources,
            such as the arm64 iOS simulator runtimes of 4.7.2 or the Android debug runtimes.
            Each recipe is configured and compiled only when a build selects its slot.
            Catalogued versions only; an uncatalogued version builds nothing.
            """,
        default = True,
    ),
    "engine": _ENGINE_ATTR,
}

_SOURCE_ATTRS = {
    "name": attr.string(doc = "Repository name; source_build tags name its `:source.json`.", mandatory = True),
    "urls": attr.string_list(doc = "Ordered mirror URLs of the same archive.", mandatory = True),
    "sha256": attr.string(doc = "SHA-256 digest of the archive.", mandatory = True),
    "strip_prefix": attr.string(doc = "Top-level directory removed on extraction."),
    "version": attr.string(
        doc = "Canonical Godot version of the sources, as their version.py names it.",
        mandatory = True,
    ),
}

_SOURCE_BUILD_ATTRS = {
    "name": attr.string(doc = "Hub repository name and prefix of the recipe repositories.", mandatory = True),
    "source": attr.label(
        doc = "The `:source.json` of a godot_engines.source or godot_engine_source repository.",
        mandatory = True,
    ),
    "platforms": attr.string_list(doc = "Nonempty list of linux, macos, android or ios.", mandatory = True),
    "cpus": attr.string_list(doc = "Optional arm64/x86_64 filter; empty selects all."),
    "build_targets": attr.string_list(doc = "Optional editor/template_debug/template_release filter; empty selects all."),
    "ios_environments": attr.string_list(doc = "Optional device/simulator filter for iOS rows; empty selects both."),
    "enabled_modules": attr.string_list(
        doc = "Enabled Godot modules; dependencies come from the source's module graph.",
        default = ["gdscript", "text_server_fb"],
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
    "build_options": attr.string_dict(doc = "Upstream configure options, as for godot_engine_build."),
    "build_name": attr.string(doc = "Build name the engines report in their version.", default = "custom"),
    "python": attr.label(doc = "Optional declared Python for configure-only graph capture.", allow_single_file = True),
    "configure_timeout": attr.int(doc = "Maximum configure duration per recipe, in seconds.", default = 600),
    "engine": _ENGINE_ATTR,
    "lock_file": attr.label(doc = """
        Optional lock file that pins every recipe's build graph, such as
        `//engines:godot_custom.lock.json`. With it, no recipe is configured on this host;
        `bazel run @<name>//:pin` writes it, configuring each recipe on an execution platform
        Godot accepts, such as a remote Linux executor for Linux recipes.
        """),
}

_ENGINE_TAG_ATTRIBUTES = {
    "prebuilt": _PREBUILT_ATTRS.keys(),
    "source": _SOURCE_ATTRS.keys(),
    "source_build": _SOURCE_BUILD_ATTRS.keys(),
}

# The repository rules and macros that plan_engines declarations name.
_ENGINE_RULES = {
    "engine_hub": engine_hub,
    "godot_android_shell": godot_android_shell,
    "godot_editor_archive": godot_editor_archive,
    "godot_engine_build": godot_engine_build,
    "godot_engine_source": godot_engine_source,
    "godot_engine_source_build": godot_engine_source_build,
    "godot_export_templates_archive": godot_export_templates_archive,
    "http_file": http_file,
}

def _engines_impl(module_ctx):
    for declaration in plan_engines(module_ctx.modules, tag_attributes = _ENGINE_TAG_ATTRIBUTES):
        _ENGINE_RULES[declaration.rule](**declaration.attrs)
    return module_ctx.extension_metadata(reproducible = True)

godot_engines = module_extension(
    doc = """
    Declare Godot engines and generate their registration hubs.

    The prebuilt tag acquires one version's editors and export templates, from the
    built-in catalogue or from explicit pins, and generates a hub whose `toolchains`
    package declares one public component per slot. The source tag acquires an immutable
    source archive; the source_build tag builds source recipes from it for the slots it selects and generates a hub
    of the same layout. Register hubs from the root module; registration order decides
    between candidates for the same slot. Hubs use only public primitives: the archive,
    source and recipe repository rules and the component macros. Downloads and
    configuration happen only for payloads a build requests.

    Example (MODULE.bazel):
    ```starlark
    godot_engines = use_extension("@autoload_rules_godot//godot:extensions.bzl", "godot_engines")
    godot_engines.prebuilt(name = "godot_prebuilt", version = "4.7.2")
    godot_engines.source(
        name = "godot_sources",
        sha256 = "e954996374cbd1cb5d72e0e3781cc537408e6ce73b010b12c6c2f308a820690a",
        strip_prefix = "godot-4.7.2-stable",
        urls = ["https://github.com/godotengine/godot/archive/refs/tags/4.7.2-stable.tar.gz"],
        version = "4.7.2",
    )
    godot_engines.source_build(
        name = "godot_source_build",
        platforms = ["ios"],
        source = "@godot_sources//:source.json",
    )
    use_repo(godot_engines, "godot_source_build", "godot_prebuilt", "godot_sources")
    register_toolchains(
        "@godot_source_build//toolchains:all",  # wins for the iOS slots it covers
        "@godot_prebuilt//toolchains:all",
    )
    ```

    A root request owns its name; identical dependency requests share repositories and
    conflicting ones fail. See [engines](../../engine.md).

    ### Default outputs
    | kind | cardinality | availability | behavior |
    | --- | --- | --- | --- |
    | repository | none | always | repository creation; generated entrypoints described above |

    ### Output groups
    none

    ### Generated targets
    | name | kind | purpose | reason | visibility | testonly | prerequisites | availability |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | @{repository}//toolchains:editor_{platform}_{cpu} | files | operation | the editor component of one editor slot; register the package with :all | public | false | editor archive for the editor platform | always |
    | @{repository}//toolchains:runtime_linux_{cpu}_{variant} | files | operation | the Linux runtime component of one runtime slot | public | false | template archive contains the slot | desktop |
    | @{repository}//toolchains:runtime_macos_{cpu}_{variant} | files | operation | the macOS runtime component of one runtime slot | public | false | template archive contains the slot | desktop |
    | @{repository}//toolchains:runtime_ios_{cpu}_{environment}_{variant} | files | operation | the iOS runtime component of one device or simulator slot | public | false | template archive contains the slot | ios |
    | @{repository}//toolchains:runtime_android_{cpu}_{variant} | files | operation | the Android runtime component of one slot | public | false | Android shell AAR pinned | android_shell |
    | @{repository}//android:{variant} | files | operation | the Android runtime of one template variant the components use | public | false | Android shell library pinned or a source build with Android rows | android_shell |
    | @{repository}//android:plugin_api | files | operation | the shell library's classes for Android plugins to compile against, never packaged; applications package the runtime of their variant | public | false | Android shell library pinned or a source build with Android rows | android_shell |
    | @{repository}//:source.json | files | operation | the descriptor of a source tag, for source_build tags and godot_engine_build recipes | public | false | source tag | source |
    | @{repository}//:{archive} | files | operation | the archive of a source tag | public | false | source tag | source |
    | @{repository}//toolchains:editor_{platform}_{cpu}.toolchain | metadata | analysis_boundary | register one editor slot alone, ahead of or instead of the whole set | public | false | none | always |
    | @{repository}//toolchains:runtime_linux_{cpu}_{variant}.toolchain | metadata | analysis_boundary | register one runtime slot alone, ahead of or instead of the whole set | public | false | none | desktop |
    | @{repository}//toolchains:runtime_macos_{cpu}_{variant}.toolchain | metadata | analysis_boundary | register one runtime slot alone, ahead of or instead of the whole set | public | false | none | desktop |
    | @{repository}//toolchains:runtime_ios_{cpu}_{environment}_{variant}.toolchain | metadata | analysis_boundary | register one runtime slot alone, ahead of or instead of the whole set | public | false | none | ios |
    | @{repository}//toolchains:runtime_android_{cpu}_{variant}.toolchain | metadata | analysis_boundary | register one runtime slot alone, ahead of or instead of the whole set | public | false | none | android_shell |

    ### Providers
    none
    """,
    implementation = _engines_impl,
    tag_classes = {
        "prebuilt": tag_class(
            doc = """
            Acquire one version's prebuilt editors and export templates and generate a hub.
            Catalogued versions need only version; explicit pins replace catalogue entries.
            """,
            attrs = _PREBUILT_ATTRS,
        ),
        "source": tag_class(
            doc = "Acquire one immutable source archive, as godot_engine_source does.",
            attrs = _SOURCE_ATTRS,
        ),
        "source_build": tag_class(
            doc = """
            Build one source build and generate its hub, as godot_engine_source_build does:
            one source recipe and one component per valid slot the filters select.
            """,
            attrs = _SOURCE_BUILD_ATTRS,
        ),
    },
)

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

    ### Default outputs
    | kind | cardinality | availability | behavior |
    | --- | --- | --- | --- |
    | repository | none | always | repository creation; generated entrypoints described below |

    ### Output groups
    none

    ### Generated targets
    | name | kind | purpose | reason | visibility | testonly | prerequisites | availability |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | @android_toolchains//:ndk_{target_system} | metadata | analysis_boundary | the C++ toolchain of this host's NDK for one Android CPU, on this host's operating system; register the package with :all | public | false | ANDROID_NDK_HOME | always |
    | @android_toolchains//:ndk_linux_x86_64_{target_system} | metadata | analysis_boundary | the C++ toolchain of the Linux NDK for one Android CPU, on linux/x86_64 execution platforms; this host's NDK on a Linux host | public | false | none | always |
    | @android_toolchains//:sdk_linux_x86_64 | metadata | analysis_boundary | the Linux SDK of the selected API level, on linux/x86_64 execution platforms; this host's SDK on a Linux host | public | false | none | always |
    | @android_toolchains//:android_linux_x86_64 | metadata | analysis_boundary | rules_android's Android toolchain with the Linux aapt2, on linux/x86_64 execution platforms; rules_android's default on a Linux host | public | false | none | always |
    | @android_toolchains//:aapt | executable | operation | aapt of the configured platform's SDK, the Linux SDK's for linux/x86_64 and this host's otherwise, for the data of a test that inspects an application on its execution platform | public | false | ANDROID_HOME | always |
    | @android_toolchains//:aapt2 | executable | operation | aapt2 of the configured platform's SDK, as :aapt | public | false | ANDROID_HOME | always |

    ### Providers
    none
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
