"""
The engine tree: one source archive's Godot sources, extracted once for every recipe of
every engine that builds from it.

This file defines godot_engine_tree apart from the recipes' rules. Bazel keys a repository
on the code of the file that defines its rule, so a change to the recipes' rules, the
engine profiles or the rendering tools renders the recipes again without extracting the
sources again.

Errors go through `_fail`, so a Starlark unit test with a mocked repository_ctx collects
them; an implementation returns after an error.
"""

load(":engine_tools.bzl", "engine_tool")

visibility(["//godot/..."])

_SCONS_URL = "https://files.pythonhosted.org/packages/7d/c9/2f430bb39e4eccba32ce8008df4a3206df651276422204e177a09e12b30b/scons-4.10.1.tar.gz"

_SCONS_SHA256 = "99c0e94a42a2c1182fa6859b0be697953db07ba936ecc9817ae0d218ced20b15"

def engine_tree_impl(ctx, *, _fail = fail):
    """
    Extract one source archive, add SCons and make the files read-only for the recipes.

    Args:
        ctx: Repository rule context of godot_engine_tree.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible, since the digest-pinned archive
        determines it.
    """
    ctx.watch(ctx.path(ctx.attr._tree))
    descriptor = json.decode(ctx.read(ctx.path(ctx.attr.source)))
    archive = ctx.attr.source.same_package_label(descriptor["archive"])
    ctx.extract(ctx.path(archive), stripPrefix = descriptor["strip_prefix"])
    ctx.download_and_extract(
        url = _SCONS_URL,
        sha256 = _SCONS_SHA256,
        stripPrefix = "scons-4.10.1",
        output = "_scons",
    )
    tool = engine_tool(ctx, ctx.attr._tree)
    result = ctx.execute(tool.command + ["--root", "."], environment = tool.environment)
    if result.return_code:
        _fail("%s: preparing the engine tree failed:\n%s\n%s" % (ctx.attr.name, result.stdout, result.stderr))
        return None

    # Recipes read this file; the digest of the tree's paths and contents prepares them
    # again whatever changes the tree.
    ctx.file("tree.json", json.encode_indent(descriptor | {
        "archive": str(archive),
        "digest": result.stdout.strip(),
    }) + "\n")
    ctx.file("BUILD.bazel", 'exports_files(["tree.json"])\n')
    return ctx.repo_metadata(reproducible = True)

godot_engine_tree = repository_rule(
    doc = """
    Extract one Godot source archive once, for every source recipe that builds from it.

    Call through use_repo_rule in MODULE.bazel, or from a module extension; godot_engines
    declares one per source archive, which the engines of that source share. The
    repository extracts the archive of a godot_engine_source descriptor, adds SCons and
    makes the files read-only; it holds upstream's files only. Each godot_engine_build
    recipe and godot_android_shell takes its `:tree.json` as `tree`: their repositories
    hold the generated build files and link the tree's files hard instead of extracting
    the sources again, and they apply their engine's patches to copies of their own of the
    files those patches touch, so a recipe costs a few megabytes. Fetching runs
    rules_python's Python 3.14. Bazel's repo contents cache, local or remote, reuses the
    tree.

    Example (MODULE.bazel):
    ```starlark
    godot_engine_tree = use_repo_rule(
        "@autoload_rules_godot//godot/engine/private:repositories.bzl", "godot_engine_tree",
    )
    godot_engine_tree(
        name = "godot_tree",
        source = "@godot_sources//:source.json",
    )
    ```
    """,
    implementation = engine_tree_impl,
    attrs = {
        "source": attr.label(
            doc = "The `:source.json` descriptor of a godot_engine_source repository.",
            mandatory = True,
            allow_single_file = [".json"],
        ),
        "_python": attr.label(default = Label("@python_3_14_host//:python")),
        "_tree": attr.label(default = Label("//tools/engine:tree.py")),
    },
)
