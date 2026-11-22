"""Optional, checksum-pinned godot-cpp repository built with rules_cc."""

load(
    "//godot/extension/private:godot_cpp.bzl",
    "GODOT_CPP_COMMIT",
    "GODOT_CPP_SHA256",
    "godot_cpp_bindings_impl",
)

godot_cpp_bindings = repository_rule(
    doc = """
    Fetch upstream godot-cpp and generate rules_cc build targets without host
    SCons/CMake/Python at repository evaluation.

    Call through use_repo_rule in MODULE.bazel. Generates :godot_cpp, a C++ library
    with declared generated bindings. Generation and compilation run as Bazel
    actions, using the pinned build Python; only patch application needs the host
    patch tool. Floating-point precision must match the engine build.

    Example (MODULE.bazel):
    ```starlark
    godot_cpp_bindings = use_repo_rule(
        "@autoload_rules_godot//godot/extension:repositories.bzl", "godot_cpp_bindings",
    )
    godot_cpp_bindings(name = "godot_cpp", enabled_classes = ["Node"])
    ```

    Use `deps = ["@godot_cpp//:godot_cpp"]` in godot_cc_extension to compile and
    link against the repository's generated bindings and upstream C++ library.
    The repository name determines the dependency label; with name = "godot_cpp", the
    public library target is @godot_cpp//:godot_cpp. Its CcInfo propagates headers,
    include paths and link inputs through the C++ toolchain.

    See [godot-cpp integration](../../gdextension.md).

    ### Default outputs
    - repository (none): repository creation; generated entrypoints described above

    ### Generated targets
    - `@{repository}//:godot_cpp` (library): link the generated C++ bindings through CcInfo
      - prerequisites: repository acquired
    - `@{repository}//:{api_path}` (files): inspect the selected upstream extension API dataset
      - prerequisites: repository acquired
    - `@{repository}//:LICENSE.md` (files): distribute the upstream binding license
      - prerequisites: repository acquired
    """,
    implementation = godot_cpp_bindings_impl,
    attrs = {
        "urls": attr.string_list(
            doc = "Ordered download URLs for the same checksum-pinned upstream archive.",
            default = [
                "https://codeload.github.com/godotengine/godot-cpp/tar.gz/" + GODOT_CPP_COMMIT,
            ],
        ),
        "sha256": attr.string(
            doc = """
            SHA-256 digest of the archive; update together with urls when using a custom
            version.
            """,
            default = GODOT_CPP_SHA256,
        ),
        "strip_prefix": attr.string(
            doc = """
            Directory prefix removed from paths; for archives this must match their
            top-level directory.
            """,
            default = "godot-cpp-" + GODOT_CPP_COMMIT,
        ),
        "patches": attr.label_list(
            doc = """
            Patch files applied in order; any rejected or ambiguous hunk fails repository
            setup.
            """,
            allow_files = True,
        ),
        "patch_strip": attr.int(
            doc = "Number of leading path components removed from each patch filename.",
            default = 1,
        ),
        "api_path": attr.string(
            doc = """
            Path within godot-cpp to the extension API JSON selected for binding
            generation.
            """,
            default = "gdextension/extension_api-4-7.json",
        ),
        "enabled_classes": attr.string_list(
            doc = """
            Upstream build-profile whitelist; required core classes and ancestors are
            retained.
            """,
        ),
        "bits": attr.string(
            doc = "Pointer width for generated bindings, 32 or 64.",
            default = "64",
            values = ["32", "64"],
        ),
        "precision": attr.string(
            doc = "Floating-point precision, single or double; must match the engine.",
            default = "single",
            values = ["single", "double"],
        ),
        "debug_features": attr.bool(
            doc = """
            Match upstream template_debug behavior; disable for release-only bindings.
            """,
            default = True,
        ),
        "_defs": attr.label(default = Label("//godot/extension/private:bindings.bzl")),
        "_cc_library": attr.label(default = Label("@rules_cc//cc:cc_library.bzl")),
        "_windows_constraint": attr.label(default = Label("@platforms//os:windows")),
        "_build_template": attr.label(default = Label("//godot/extension:godot_cpp.BUILD.tpl")),
    },
)
