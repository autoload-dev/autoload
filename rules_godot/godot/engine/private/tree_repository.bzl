"""
The engine tree: one engine's Godot sources, extracted and patched once for all its recipes.

This file defines godot_engine_tree apart from the recipes' rules and loads only the
patching it needs. Bazel keys a repository on the code of the file that defines its rule,
so a change to the recipes' rules, the engine profiles or the rendering tools renders the
recipes again without extracting the sources again.

Errors go through `_fail`, so a Starlark unit test with a mocked repository_ctx collects
them; an implementation returns after an error.
"""

load("//godot/private:patches.bzl", "apply_repository_patches")

visibility(["//godot/..."])

_SCONS_URL = "https://files.pythonhosted.org/packages/7d/c9/2f430bb39e4eccba32ce8008df4a3206df651276422204e177a09e12b30b/scons-4.10.1.tar.gz"

_SCONS_SHA256 = "99c0e94a42a2c1182fa6859b0be697953db07ba936ecc9817ae0d218ced20b15"

def engine_tree_impl(ctx, *, _fail = fail):
    """
    Extract and patch one engine's sources, add SCons and prepare the files for the recipes.

    Args:
        ctx: Repository rule context of godot_engine_tree.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible, since the digest-pinned archive and the
        patches determine it.
    """
    tool = ctx.path(ctx.attr._tree)
    ctx.watch(tool)
    descriptor = json.decode(ctx.read(ctx.path(ctx.attr.source)))
    archive = ctx.attr.source.same_package_label(descriptor["archive"])
    ctx.extract(ctx.path(archive), stripPrefix = descriptor["strip_prefix"])
    if not apply_repository_patches(ctx, _fail = _fail):
        return None
    ctx.download_and_extract(
        url = _SCONS_URL,
        sha256 = _SCONS_SHA256,
        stripPrefix = "scons-4.10.1",
        output = "_scons",
    )
    result = ctx.execute([str(ctx.path(ctx.attr._python)), str(tool), "prepare", "--root", "."])
    if result.return_code:
        _fail("%s: preparing the engine tree failed:\n%s\n%s" % (ctx.attr.name, result.stdout, result.stderr))
        return None

    # Recipes read this file, so whatever changes the tree configures them again.
    ctx.file("tree.json", json.encode_indent(descriptor | {
        "archive": str(archive),
        "patches": [str(patch) for patch in ctx.attr.patches],
        "patch_strip": ctx.attr.patch_strip,
        "scons": _SCONS_SHA256,
    }) + "\n")
    ctx.file("BUILD.bazel", 'exports_files(["tree.json"])\n')
    return ctx.repo_metadata(reproducible = True)

godot_engine_tree = repository_rule(
    doc = """
    Extract and patch one engine's Godot sources once, for all its source recipes.

    Call through use_repo_rule in MODULE.bazel, or from a module extension; godot_engines
    declares one per engine that builds from source, `@<name>_tree`. The repository
    extracts the archive of a godot_engine_source descriptor, applies the patches of the
    engine's build policy with strict matching, adds SCons and makes the files read-only.
    Each godot_engine_build recipe and the godot_android_shell of the engine take its
    `:tree.json` as `tree`: their repositories hold the generated build files and link the
    tree's files hard instead of extracting the sources again, so a recipe costs a few
    megabytes. Fetching runs rules_python's Python 3.14 and needs patch when patches are
    supplied. Bazel's repo contents cache, local or remote, reuses the tree.

    Example (MODULE.bazel):
    ```starlark
    godot_engine_tree = use_repo_rule(
        "@autoload_rules_godot//godot/engine/private:repositories.bzl", "godot_engine_tree",
    )
    godot_engine_tree(
        name = "godot_tree",
        patches = ["//engines:engine-name.patch"],
        source = "@godot_sources//:source.json",
    )
    ```

    A rejected or ambiguous patch hunk fails the tree.
    """,
    implementation = engine_tree_impl,
    attrs = {
        "source": attr.label(
            doc = "The `:source.json` descriptor of a godot_engine_source repository.",
            mandatory = True,
            allow_single_file = [".json"],
        ),
        "patches": attr.label_list(
            doc = """
            Patch files applied in order to the sources of every recipe and the Android
            shell; any rejected or ambiguous hunk fails the tree.
            """,
            allow_files = [".patch", ".diff"],
        ),
        "patch_strip": attr.int(
            doc = "Number of leading path components removed from each patch filename.",
            default = 1,
        ),
        "_python": attr.label(default = Label("@python_3_14_host//:python")),
        "_tree": attr.label(default = Label("//tools/engine:tree.py")),
    },
)
