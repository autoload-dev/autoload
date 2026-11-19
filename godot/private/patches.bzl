"""Apply source patches strictly, without the lossy fuzz matching of Bazel's built-in patching."""

visibility(["//godot/engine/private", "//godot/extension/private", "//godot/private/tests"])

def apply_repository_patches(ctx, *, _fail = fail):
    """
    Apply every declared patch or stop before configuring the source tree.

    Args:
        ctx: Repository context with patches and patch_strip attributes.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        True when every patch applied; False after an error.
    """
    if not ctx.attr.patches:
        return True
    ctx.getenv("PATH")
    patch_tool = ctx.which("patch")
    if not patch_tool:
        _fail("Applying source patches requires the patch command on PATH")
        return False
    for patch in ctx.attr.patches:
        patch_file = ctx.path(patch)
        ctx.watch(patch_file)

        # Bazel 9.3's built-in fuzz matching can discard changed lines. The
        # established patch tool rejects mismatched hunks with fuzz disabled.
        result = ctx.execute([
            str(patch_tool),
            "-p%s" % ctx.attr.patch_strip,
            "-F0",
            "-t",
            "-N",
            "-i",
            str(patch_file),
        ])
        if result.return_code:
            _fail("Error applying patch %s (strict matching, fuzz disabled):\n%s%s" % (
                patch,
                result.stdout,
                result.stderr,
            ))
            return False
    return True
