"""
The repository of the libraries one Godot COPYRIGHT.txt lists, each a package of its own.

godot_engines declares one per COPYRIGHT.txt, which every engine of that file shares: for a
catalogued release, from the file the catalogue pins for the release's commit, and for
other sources, from their engine tree's file. The repositories that hold Godot's binaries
name its `:bundled_packages` from their own package metadata.
"""

load("//godot/private:supply_chain.bzl", "write_bundled_packages")

visibility(["//godot/..."])

def bundled_packages_impl(ctx, *, _fail = fail):
    """
    Declare the libraries of a COPYRIGHT.txt, downloaded or beside an engine tree's descriptor.

    Args:
        ctx: Repository rule context of godot_bundled_packages.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible, since the digest-pinned file or tree
        determines it.
    """
    if bool(ctx.attr.urls) == bool(ctx.attr.tree):
        _fail("%s: set exactly one of urls and tree" % ctx.attr.name)
        return None
    if ctx.attr.urls:
        ctx.download(url = ctx.attr.urls, output = "COPYRIGHT.txt", sha256 = ctx.attr.sha256)
        copyright = "COPYRIGHT.txt"
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
        "urls": attr.string_list(
            doc = "Mirror URLs of Godot's COPYRIGHT.txt, such as of the file at a release's commit.",
        ),
        "sha256": attr.string(doc = "SHA-256 digest of the COPYRIGHT.txt the urls name."),
        "tree": attr.label(
            doc = "The `:tree.json` of a godot_engine_tree, beside which the tree's COPYRIGHT.txt lies.",
            allow_single_file = [".json"],
        ),
    },
)
