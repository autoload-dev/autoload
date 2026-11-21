"""
Engine acquisition: immutable sources and configure-only source recipes.

godot_engines declares these repositories through its source and source_build tags; the
ruleset's own test fixtures also declare them directly.
"""

load("//godot/engine/private:hub.bzl", "engine_hub")
load("//godot/engine/private:source_build_rows.bzl", "source_build_declarations")
load(
    "//godot/engine/private:source_repositories.bzl",
    "android_shell_impl",
    "engine_build_impl",
    "engine_source_impl",
)

visibility(["//..."])

godot_engine_source = repository_rule(
    doc = """
    Acquire one immutable Godot source archive for godot_engine_build recipes.

    Call through use_repo_rule in MODULE.bazel, or from a module extension. The
    repository exports `:source.json`, the descriptor recipes take as `source`, and the
    archive itself; it never extracts or configures the sources. Upstream releases and
    fork archives alike are pinned by digest and their canonical Godot version, which
    every recipe checks against the extracted version.py.

    Example (MODULE.bazel):
    ```starlark
    godot_engine_source = use_repo_rule(
        "@autoload_rules_godot//godot/engine/private:repositories.bzl", "godot_engine_source",
    )
    godot_engine_source(
        name = "godot_sources",
        sha256 = "e954996374cbd1cb5d72e0e3781cc537408e6ce73b010b12c6c2f308a820690a",
        strip_prefix = "godot-4.7.2-stable",
        urls = ["https://github.com/godotengine/godot/archive/refs/tags/4.7.2-stable.tar.gz"],
        version = "4.7.2",
    )
    ```

    ### Default outputs
    - repository (none): repository creation; generated entrypoints described above

    ### Generated targets
    - `@{repository}//:source.json` (files): the source descriptor godot_engine_build recipes take as source
      - prerequisites: archive acquired
    - `@{repository}//:{archive}` (files): the acquired archive, which recipes extract independently
      - prerequisites: archive acquired
    """,
    implementation = engine_source_impl,
    attrs = {
        "urls": attr.string_list(
            doc = "Ordered mirror URLs of the same archive; the first one's suffix names its type.",
            mandatory = True,
        ),
        "sha256": attr.string(doc = "SHA-256 digest of the archive.", mandatory = True),
        "strip_prefix": attr.string(doc = "Top-level directory removed on extraction."),
        "version": attr.string(
            doc = "Canonical Godot version of the sources, such as 4.7.2 or 4.8.0-beta1.",
            mandatory = True,
        ),
    },
)

godot_engine_build = repository_rule(
    doc = """
    Configure one fixed Godot source recipe and emit granular rules_cc build targets.

    Call through use_repo_rule in MODULE.bazel, or from a module extension. The recipe
    extracts the archive of a godot_engine_source descriptor into its own repository,
    applies the patches, adds the modules and captures the upstream build graph; SCons
    never compiles. Compilation runs later as Bazel actions, only for the outputs a build
    requests. The recipe registers nothing: name its outputs as component payloads.
    Fetching needs host Python 3.9+ (or the python attribute), patch when patches are
    supplied, and the target operating system's SDK. Bazel's repo contents cache, local
    or remote (--experimental_remote_repo_contents_cache), reuses Android, iOS and macOS
    recipes; Linux recipes configure on every host, because Godot enables Linux features
    by the packages installed there.

    Example (MODULE.bazel):
    ```starlark
    godot_engine_build = use_repo_rule(
        "@autoload_rules_godot//godot/engine/private:repositories.bzl", "godot_engine_build",
    )
    godot_engine_build(
        name = "godot_macos_arm64_release",
        cpu = "arm64",
        build_target = "template_release",
        platform = "macos",
        source = "@godot_sources//:source.json",
    )
    ```

    A source contradicting the descriptor's version, unknown or rules_godot-controlled
    options, unresolvable modules and rejected patch hunks fail the recipe. See
    [source-built engines](../../engine.md) for custom modules, options and patches.

    ### Default outputs
    - repository (none): repository creation; generated entrypoints described above

    ### Generated targets
    - `@{repository}//:godot` (executable): the desktop editor or template executable, a component payload
      - prerequisites: desktop recipe
      - availability: desktop
    - `@{repository}//:godot` (files): the Android engine library with provenance
      - prerequisites: Android recipe
      - availability: android
    - `@{repository}//:engine_library` (library): link the engine library through CcInfo; the iOS component payload
      - prerequisites: recipe configured with the owning operating system's SDK
    - `@{repository}//:libgodot_android.so` (library): the Android engine library, godot_android_runtime's engine_library
      - prerequisites: Android recipe
      - availability: android
    - `@{repository}//:engine_manifest.json` (files): inspect captured SCons configuration facts
      - prerequisites: recipe configured
    """,
    implementation = engine_build_impl,
    attrs = {
        "source": attr.label(
            doc = "The `:source.json` descriptor of a godot_engine_source repository.",
            mandatory = True,
            allow_single_file = [".json"],
        ),
        "platform": attr.string(
            doc = "Target operating system: linux, macos, android or ios.",
            mandatory = True,
            values = ["linux", "macos", "android", "ios"],
        ),
        "cpu": attr.string(
            doc = "Target CPU, such as arm64 or x86_64.",
            mandatory = True,
        ),
        "build_target": attr.string(
            doc = "Godot build target: editor, template_debug or template_release.",
            mandatory = True,
            values = ["editor", "template_debug", "template_release"],
        ),
        "environment": attr.string(
            doc = "iOS environment, device or simulator; required for iOS and empty elsewhere.",
            values = ["", "device", "simulator"],
        ),
        "enabled_modules": attr.string_list(
            doc = "Enabled Godot modules; their dependencies come from the source's module graph.",
            default = ["gdscript", "text_server_fb"],
        ),
        "default_modules": attr.bool(
            doc = """
            Also enable every module Godot enables by default for the platform, as its
            official builds do; `enabled_modules` must then name only modules Godot can build.
            """,
        ),
        "custom_modules": attr.label_keyed_string_dict(
            doc = """
            Each custom module's config.py label mapped to its module name; the containing
            source tree is watched.
            """,
            allow_files = [".py"],
        ),
        "patches": attr.label_list(
            doc = "Patch files applied in order; any rejected or ambiguous hunk fails the recipe.",
            allow_files = [".patch", ".diff"],
        ),
        "patch_strip": attr.int(
            doc = "Number of leading path components removed from each patch filename.",
            default = 1,
        ),
        "build_options": attr.string_dict(
            doc = """
            Upstream configure options as string values; import_env_vars lists
            comma-separated environment dependencies. Options rules_godot controls, such as
            platform, arch, target, the iOS simulator switch and module selection, are
            rejected; optimize and debug_symbols follow Bazel's -c, --copt and --per_file_copt.
            """,
        ),
        "build_name": attr.string(
            doc = """
            Build name the engine reports in its version, followed by where its hash
            comes from, such as 4.7.2.stable.custom-git.<hash>; letters, digits and
            underscores.
            """,
            default = "custom",
        ),
        "python": attr.label(
            doc = """
            Optional declared Python executable for configure-only graph translation;
            otherwise uses python3 on PATH (Python 3.9+).
            """,
            allow_single_file = True,
        ),
        "configure_timeout": attr.int(
            doc = "Maximum configure-only subprocess duration in seconds.",
            default = 600,
        ),
        "lock_file": attr.label(
            doc = """
            The lock file that pins this recipe's build graph, as a source build's lock_file
            names it. With it, the repository configures nothing on this host and declares
            `:pin`, which configures the recipe on an execution platform Godot accepts.
            """,
        ),
        "lock_key": attr.string(doc = "The recipe's key in the lock file, such as linux_x86_64_editor."),
        "repin": attr.string(doc = "The target that repins the lock file, named by a stale recipe's error."),
        "_configure": attr.label(default = Label("//tools/engine:configure.py")),
        "_pin_bzl": attr.label(default = Label("//godot/engine/private:pin.bzl")),
        "_generator": attr.label(default = Label("//godot/engine/private:generator.bzl")),
        "_module_graph": attr.label(default = Label("//tools/engine:module_graph.py")),
        "_cc_rules": attr.label(default = Label("@rules_cc//cc:cc_library.bzl")),
        "_platforms_constraint": attr.label(default = Label("@platforms//os:android")),
        "_apple_constraint": attr.label(
            default = Label("@apple_support//constraints:device"),
        ),
        "_swift_library": attr.label(
            default = Label("@rules_swift//swift:swift_library.bzl"),
        ),
    },
    configure = True,
    environ = [
        "DEVELOPER_DIR",
        "SDKROOT",
        "PATH",
        "PKG_CONFIG_PATH",
        "GODOT_VERSION_STATUS",
        "SCRIPT_AES256_ENCRYPTION_KEY",
    ],
)

godot_android_shell = repository_rule(
    doc = """
    Build Godot's Java/Kotlin Android shell library from a source descriptor.

    Call through use_repo_rule in MODULE.bazel, or from a module extension. The
    repository extracts the source, applies the patches and exposes `:debug` and
    `:release`, the Android shell library of each template variant built with rules_android and
    rules_kotlin; their `.aar` outputs, such as `:release.aar`, are godot_android_runtime
    shells. Java and Kotlin target Godot's language level per target, so no Kotlin
    toolchain is registered. The shell library's Maven dependencies come from autoload_rules_godot's
    contribution to the shared `maven` repository; repin after adding autoload_rules_godot.

    Example (MODULE.bazel):
    ```starlark
    godot_android_shell = use_repo_rule(
        "@autoload_rules_godot//godot/engine/private:repositories.bzl", "godot_android_shell",
    )
    godot_android_shell(name = "godot_shell", source = "@godot_sources//:source.json")
    ```

    ### Default outputs
    - repository (none): repository creation; generated entrypoints described above

    ### Generated targets
    - `@{repository}//:{variant}` (files): the Android shell library of one template variant; its .aar output is a godot_android_runtime shell
      - prerequisites: Android SDK
    """,
    implementation = android_shell_impl,
    attrs = {
        "source": attr.label(
            doc = "The `:source.json` descriptor of a godot_engine_source repository.",
            mandatory = True,
            allow_single_file = [".json"],
        ),
        "patches": attr.label_list(
            doc = "Patch files applied in order, such as a fork's Java changes.",
            allow_files = [".patch", ".diff"],
        ),
        "patch_strip": attr.int(
            doc = "Number of leading path components removed from each patch filename.",
            default = 1,
        ),
        "_build_template": attr.label(default = Label("//godot/engine/private:android_shell.BUILD.tpl")),
        "_kotlin_android": attr.label(default = Label("@rules_kotlin//kotlin:android.bzl")),
        "_kotlin_core": attr.label(default = Label("@rules_kotlin//kotlin:core.bzl")),
    },
)

# The repository rules that source_build_declarations names.
_SOURCE_BUILD_RULES = {
    "engine_hub": engine_hub,
    "godot_android_shell": godot_android_shell,
    "godot_engine_build": godot_engine_build,
}

def godot_engine_source_build(
        name,
        source,
        platforms,
        cpus = [],
        build_targets = [],
        ios_environments = [],
        enabled_modules = ["gdscript", "text_server_fb"],
        default_modules = False,
        custom_modules = {},
        patches = [],
        patch_strip = 1,
        build_options = {},
        build_name = "custom",
        python = None,
        configure_timeout = 600,
        lock_file = None,
        engine = ""):
    """
    Declare a source build: its source recipes and its hub, from a module extension.

    Call during a module extension's implementation; the helper declares repositories and
    cannot run in BUILD files. It applies one build policy to the valid rows its filters
    select: one godot_engine_build per row, named `<name>_<platform>_<cpu>[_<environment>]_<build_target>`,
    for Android one godot_android_shell named `<name>_android_shell` with the same patches,
    and the hub `<name>` with one component per slot in `@<name>//toolchains`, registered
    through `@<name>//toolchains:all`. Common inputs apply to every row; declaring the
    source build configures no recipe until a build requests its payload.

    Example (an extension implementation):
    ```starlark
    godot_engine_source_build(
        name = "godot_source_build",
        source = "@godot_sources//:source.json",
        platforms = ["macos", "ios"],
        build_targets = ["editor", "template_release"],
    )
    ```

    ### Default outputs
    - repository (none): repository creation; generated entrypoints described above

    ### Generated targets
    - `@{repository}//toolchains:editor_{platform}_{cpu}` (files): the editor component of one selected editor row
      - prerequisites: editor row selected
      - availability: editor
    - `@{repository}//toolchains:runtime_{platform}_{cpu}_{variant}` (files): the runtime component of one selected Linux or macOS template row
      - prerequisites: desktop row selected
      - availability: desktop
    - `@{repository}//toolchains:runtime_ios_{cpu}_{environment}_{variant}` (files): the runtime component of one selected iOS template row
      - prerequisites: iOS row selected
      - availability: ios
    - `@{repository}//toolchains:runtime_android_{cpu}_{variant}` (files): the runtime component of one selected Android template row
      - prerequisites: Android row selected
      - availability: android
    - `@{repository}//android:{variant}` (files): the Android runtime of one template variant: the source build's Android shell library with each CPU's engine library
      - prerequisites: Android row selected
      - availability: android
    - `@{repository}//android:plugin_api` (files): the shell library's classes for Android plugins to compile against, never packaged; applications package the runtime of their variant
      - prerequisites: Android row selected
      - availability: android
    - `@{repository}//toolchains:editor_{platform}_{cpu}.toolchain` (metadata): register one editor slot alone
      - purpose: analysis_boundary
      - availability: editor
    - `@{repository}//toolchains:runtime_{platform}_{cpu}_{variant}.toolchain` (metadata): register one runtime slot alone
      - purpose: analysis_boundary
      - availability: desktop
    - `@{repository}//toolchains:runtime_ios_{cpu}_{environment}_{variant}.toolchain` (metadata): register one runtime slot alone
      - purpose: analysis_boundary
      - availability: ios
    - `@{repository}//toolchains:runtime_android_{cpu}_{variant}.toolchain` (metadata): register one runtime slot alone
      - purpose: analysis_boundary
      - availability: android

    Args:
        name: Hub repository name and the prefix of the generated repositories.
        source: Label of the `:source.json` descriptor of a godot_engine_source repository.
        platforms: Nonempty list of linux, macos, android or ios.
        cpus: Optional arm64/x86_64 filter; empty selects every valid CPU.
        build_targets: Optional editor/template_debug/template_release filter; empty selects all.
        ios_environments: Optional device/simulator filter for iOS rows; empty selects both.
        enabled_modules: As for godot_engine_build.
        default_modules: As for godot_engine_build.
        custom_modules: As for godot_engine_build.
        patches: As for godot_engine_build; Android shell libraries apply them too.
        patch_strip: As for godot_engine_build.
        build_options: As for godot_engine_build.
        build_name: As for godot_engine_build.
        python: As for godot_engine_build.
        configure_timeout: As for godot_engine_build.
        lock_file: Optional Label of the lock file that pins every recipe; see
            godot_engines.source_build. The hub then declares `:pin`, which writes it.
        engine: Name of the engine the hub's components belong to; empty joins the
            default engine. See godot_engines.source_build.
    """
    common = {
        "enabled_modules": enabled_modules,
        "default_modules": default_modules,
        "custom_modules": custom_modules,
        "patches": patches,
        "patch_strip": patch_strip,
        "build_options": build_options,
        "build_name": build_name,
        "python": python,
        "configure_timeout": configure_timeout,
    }
    for declaration in source_build_declarations(
        name,
        source,
        platforms,
        cpus,
        build_targets,
        ios_environments,
        common,
        lock_file = lock_file,
        engine = engine,
    ):
        _SOURCE_BUILD_RULES[declaration.rule](**declaration.attrs)
