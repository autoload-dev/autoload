"""
The metadata Godot keeps in a project's text files, one kind per flag in //godot/metadata.

Packs complete it in the copy they export; godot_metadata_sync writes it into
the checkout.
"""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")

visibility("//godot/...")

# Per kind: the text files that carry it, and the mnemonic and progress
# message of the check packs run when its flag is require.
METADATA = {
    "node_ids": struct(
        texts = (".tscn",),
        mnemonic = "GodotNodeIds",
        progress_message = "Validating %{label} (node IDs)",
    ),
    "resource_uids": struct(
        texts = (".tscn", ".tres"),
        mnemonic = "GodotResourceUids",
        progress_message = "Validating %{label} (resource UIDs)",
    ),
}

# The flags, for rules that read them through metadata_modes.
METADATA_ATTRS = {
    "_metadata_" + kind: attr.label(
        default = Label("//godot/metadata:" + kind),
        providers = [BuildSettingInfo],
    )
    for kind in METADATA
}

def metadata_kinds(ctx, modes):
    """
    Return the metadata kinds whose flag has one of modes.

    Args:
        ctx: Analysis context of a rule with METADATA_ATTRS.
        modes: Flag values, such as ["sync", "require"].

    Returns:
        The kinds, in METADATA's order.
    """
    return [kind for kind, mode in metadata_modes(ctx).items() if mode in modes]

def metadata_entry(path, kinds):
    """
    Return the manifest entry with which staging completes kinds from a metadata index.

    Args:
        path: The index's path as the action or run sees it.
        kinds: The kinds to complete; none leaves the entry out.

    Returns:
        A dict to merge into the manifest.
    """
    return {"metadata_index": {"path": path, "assign": kinds}} if kinds else {}

def metadata_modes(ctx):
    """
    Return each metadata kind's flag value: off, assign, sync or require.

    Args:
        ctx: Analysis context of a rule with METADATA_ATTRS.

    Returns:
        A dict of kind to value.
    """
    return {kind: getattr(ctx.attr, "_metadata_" + kind)[BuildSettingInfo].value for kind in METADATA}
