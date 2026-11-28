"""
The repository of the libraries one Godot COPYRIGHT.txt lists, each a package of its own.

godot_engines declares one per COPYRIGHT.txt: for the official binaries of a catalogued
version, from the file the catalogue pins, and for an engine tree, from the tree's file,
shared by every recipe of that source archive. The repositories that hold Godot's binaries
name its `:bundled_packages` from their own package metadata.
"""

load("//godot/private:supply_chain.bzl", "write_bundled_packages")

visibility(["//godot/..."])

def bundled_packages_impl(ctx, *, _fail = fail):
    """
    Declare the libraries of a COPYRIGHT.txt, given as a file or beside an engine tree's descriptor.

    Args:
        ctx: Repository rule context of godot_bundled_packages.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible, since the digest-pinned file or tree
        determines it.
    """
    if bool(ctx.attr.copyright) == bool(ctx.attr.tree):
        _fail("%s: set exactly one of copyright and tree" % ctx.attr.name)
        return None
    if ctx.attr.copyright:
        copyright = ctx.path(ctx.attr.copyright)
    else:
        copyright = "%s/COPYRIGHT.txt" % ctx.path(ctx.attr.tree).dirname
    write_bundled_packages(ctx, copyright)
    return ctx.repo_metadata(reproducible = True)

godot_bundled_packages = repository_rule(
    doc = """
    Declare each library a Godot COPYRIGHT.txt lists as a package of its own.

    `:bundled_packages` gathers the targets that carry the libraries' package metadata;
    without a COPYRIGHT.txt beside the tree, it is empty.
    """,
    implementation = bundled_packages_impl,
    attrs = {
        "copyright": attr.label(
            doc = "Godot's COPYRIGHT.txt, such as the file the catalogue pins for a release.",
            allow_single_file = True,
        ),
        "tree": attr.label(
            doc = "The `:tree.json` of a godot_engine_tree, beside which the tree's COPYRIGHT.txt lies.",
            allow_single_file = [".json"],
        ),
    },
)
