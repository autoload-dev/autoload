"""
Engine acquisition: immutable sources, the engine tree and configure-only source recipes.

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
load("//godot/engine/private:tree_repository.bzl", _godot_engine_tree = "godot_engine_tree")

visibility(["//..."])

# ==== Repository rules ========================================================

# The patches of a recipe or Android shell, which it applies to copies of its own of the
# files they touch; it links the engine tree's other files.
_PATCH_ATTRS = {
    "patches": attr.label_list(
        doc = """
        Patch files applied in order with strict matching, such as a fork's C++ or Java
        changes; any rejected or ambiguous hunk fails the repository. The repository holds
        copies of its own of the files they touch and links the tree's other files.
        """,
        allow_files = [".patch", ".diff"],
    ),
    "patch_strip": attr.int(
        doc = "Number of leading path components removed from each patch filename.",
        default = 1,
    ),
}

# Defined apart, so that a change to the rules here keeps the extracted sources.
godot_engine_tree = _godot_engine_tree

godot_engine_source = repository_rule(
    doc = """
    Acquire one immutable Godot source archive for an engine tree.

    Call through use_repo_rule in MODULE.bazel, or from a module extension. The
    repository exports `:source.json`, the descriptor godot_engine_tree takes as `source`,
    and the archive itself; it never extracts or configures the sources. Upstream releases and
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
    links the files of its source's godot_engine_tree hard into its own repository,
    applies its patches to copies of its own of the files they touch, adds the custom
    modules and captures the upstream build graph; SCons never compiles. Its repository
    holds only the files it generates or patches beside those links, a few megabytes, so
    the recipes of every engine of one source archive share one extracted copy of it.
    Compilation runs later as Bazel actions, only for the outputs a build requests. The
    recipe registers nothing: name its outputs as component payloads. Fetching runs
    rules_python's Python 3.14 and needs the target operating system's SDK. Bazel's repo
    contents cache, local or remote (--experimental_remote_repo_contents_cache), reuses
    Android, iOS and macOS recipes; Linux recipes configure on every host, because Godot
    enables Linux features by the packages installed there.

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
        tree = "@godot_tree//:tree.json",
        patches = ["//engines:engine-name.patch"],
    )
    ```

    A rejected or ambiguous patch hunk, a source contradicting the descriptor's version,
    unknown or rules_godot-controlled options and unresolvable modules fail the recipe. See
    [source-built engines](../../engine.md) for custom modules, options and patches.
    """,
    implementation = engine_build_impl,
    attrs = _PATCH_ATTRS | {
        "tree": attr.label(
            doc = """
            The `:tree.json` descriptor of the godot_engine_tree repository of the engine's
            source archive: the extracted sources the recipe patches, configures and
            compiles.
            """,
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
            Each custom module's files mapped to its module name: a target, such as a
            filegroup of `glob(["**"])`, in the package that holds the module's config.py.
            The recipe configures with the module's build scripts, shader sources and file
            paths, which it watches; its code, such as C++ sources, comes from the target
            when a build compiles it, so editing the code prepares no recipe again.
            """,
            allow_files = True,
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
        "_custom_modules": attr.label(default = Label("//tools/engine:custom_modules.py")),
        "_tree": attr.label(default = Label("//tools/engine:tree.py")),
        "_tree_link": attr.label(default = Label("//tools/engine:tree_link.py")),
        "_class_db": attr.label(default = Label("//tools/engine:class_db.py")),
        "_patches": attr.label(default = Label("//tools/engine:patches.py")),
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
    Build Godot's Java/Kotlin Android shell library from an engine tree.

    Call through use_repo_rule in MODULE.bazel, or from a module extension. The
    repository links the shell library's files of a godot_engine_tree, applies the
    engine's patches to copies of its own of the files they touch, and exposes `:debug` and
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
    godot_android_shell(
        name = "godot_shell",
        patches = ["//engines:engine-name.patch"],
        tree = "@godot_tree//:tree.json",
    )
    ```
    """,
    implementation = android_shell_impl,
    attrs = _PATCH_ATTRS | {
        "tree": attr.label(
            doc = """
            The `:tree.json` descriptor of the godot_engine_tree repository of the engine's
            source archive.
            """,
            mandatory = True,
            allow_single_file = [".json"],
        ),
        "_build_template": attr.label(default = Label("//godot/engine/private:android_shell.BUILD.tpl")),
        "_kotlin_android": attr.label(default = Label("@rules_kotlin//kotlin:android.bzl")),
        "_kotlin_core": attr.label(default = Label("@rules_kotlin//kotlin:core.bzl")),
        "_python": attr.label(default = Label("@python_3_14_host//:python")),
        "_tree": attr.label(default = Label("//tools/engine:tree.py")),
        "_tree_link": attr.label(default = Label("//tools/engine:tree_link.py")),
        "_class_db": attr.label(default = Label("//tools/engine:class_db.py")),
        "_patches": attr.label(default = Label("//tools/engine:patches.py")),
    },
)
