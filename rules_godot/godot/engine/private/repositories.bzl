"""
Engine acquisition: immutable sources and configure-only source recipes.

godot_engines declares these repositories for each engine it registers; the ruleset's own
test fixtures also declare them directly.

Sections: Repository rules.
"""

load(
    "//godot/engine/private:source_repositories.bzl",
    "android_shell_impl",
    "engine_build_impl",
    "engine_source_impl",
)

visibility(["//..."])

# ==== Repository rules ========================================================

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
    Fetching runs rules_python's Python 3.14, needs patch when patches are
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
            doc = """
            Enabled Godot modules; their dependencies come from the source's module graph.
            Empty selects `gdscript` and `text_server_fb`, or nothing beyond Godot's defaults
            with `default_modules`. An engine takes one of `text_server_adv` and
            `text_server_fb`.
            """,
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
        "renderers": attr.string_list(
            doc = """
            Godot's rendering methods the engine runs: gl_compatibility, mobile, forward_plus.
            The recipe derives the drivers from them, and applications check their project's
            method against them; see the engine guide. Empty keeps Godot's drivers.
            """,
        ),
        "build_options": attr.string_dict(
            doc = """
            Upstream configure options as string values; import_env_vars lists
            comma-separated environment dependencies. Options rules_godot controls, such as
            platform, arch, target, the iOS simulator switch and module selection, are
            rejected; optimize and lto follow //godot:engine_optimize and //godot:engine_lto,
            debug_symbols Bazel's -c, --copt and --per_file_copt.
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
        "lock_file": attr.label(
            doc = """
            The lock file that pins this recipe's build graph, as a source build's lock_file
            names it. With it, the repository configures nothing on this host and declares
            `:pin`, which configures the recipe on an execution platform Godot accepts.
            """,
        ),
        "lock_key": attr.string(doc = "The recipe's key in the lock file, such as linux_x86_64_editor."),
        "runtime_profiles": attr.string_dict(
            doc = """
            Registered runtime profiles with build options: each profile's label mapped to
            its disabled_build_options as a JSON object. The recipe declares a runtime
            variant of each, its graph configured with those build options, which an
            application whose build_profile names the profile gets.
            """,
        ),
        "repin": attr.string(doc = "The target that repins the lock file, named by a stale recipe's error."),
        "_configure": attr.label(default = Label("//tools/engine:configure.py")),
        "_python": attr.label(default = Label("@python_3_14_host//:python")),
        "_pin_bzl": attr.label(default = Label("//godot/engine/private:pin.bzl")),
        "_generator": attr.label(default = Label("//godot/engine/private:generator.bzl")),
        "_module_graph": attr.label(default = Label("//tools/engine:module_graph.py")),
        "_include_graph": attr.label(default = Label("//tools/engine:include_graph.py")),
        "_render": attr.label(default = Label("//tools/engine:render.py")),
        "_build_profile": attr.label(default = Label("//tools/engine:build_profile.py")),
        "_define_analysis": attr.label(default = Label("//tools/engine:define_analysis.py")),
        "_source_tree": attr.label(default = Label("//tools/engine:source_tree.py")),
        "_variants": attr.label(default = Label("//tools/engine:variants.py")),
        "_generators": attr.label(default = Label("//tools/engine:generators.py")),
        "_build_file": attr.label(default = Label("//tools/engine:build_file.py")),
        "_build_profile_label": attr.label(default = Label("//godot/private:build_profile_label")),
        "_cc_rules": attr.label(default = Label("@rules_cc//cc:cc_library.bzl")),
        "_platforms_constraint": attr.label(default = Label("@platforms//os:android")),
        "_apple_constraint": attr.label(
            default = Label("@apple_support//constraints:device"),
        ),
        "_swift_library": attr.label(
            default = Label("@rules_swift//swift:swift_library.bzl"),
        ),
    },
    # No `environ`: the variables a configuration reads are recorded with ctx.getenv
    # (source_repositories.bzl), so only they invalidate it, and a pinned recipe reads none.
    # Declared variables, such as a PATH that names each CI runner's own tool directory, would
    # key every recipe and configure it again wherever they differ.
    configure = True,
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
