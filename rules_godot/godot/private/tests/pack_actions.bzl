"""The Godot actions of a pack and of the export it selects, with the export's view."""

load("//godot/private:view.bzl", "GodotViewInfo")

visibility([
    "//godot/extension/tests/...",
    "//godot/private/tests/...",
])

PackActionsInfo = provider(
    doc = "Actions of a target and of what it reaches through its export edge.",
    fields = {
        "actions": "list of the actions",
        "view": "GodotViewInfo of the export's view, which the pack macro keeps private; None outside a pack",
        "native_slices": "number of platform slices the export configures its native path in",
    },
)

def _pack_actions_impl(target, ctx):
    actions = list(target.actions)
    view = None
    native_slices = 0
    if hasattr(ctx.rule.attr, "view") and hasattr(ctx.rule.attr, "native"):
        view = ctx.rule.attr.view[GodotViewInfo]
        native_slices = len(ctx.rule.attr.native)
    if hasattr(ctx.rule.attr, "export"):
        export = ctx.rule.attr.export
        for dependency in export if type(export) == "list" else [export]:
            if PackActionsInfo in dependency:
                info = dependency[PackActionsInfo]
                actions.extend(info.actions)
                view = info.view
                native_slices = info.native_slices
    return [PackActionsInfo(actions = actions, view = view, native_slices = native_slices)]

pack_actions = aspect(
    implementation = _pack_actions_impl,
    attr_aspects = ["export"],
    doc = "Collect a pack's own actions and those of its export, but not the project's.",
)

def godot_mnemonics(target):
    """Return the sorted Godot mnemonics of a target analyzed with pack_actions."""
    return sorted([
        action.mnemonic
        for action in target[PackActionsInfo].actions
        if action.mnemonic.startswith("Godot")
    ])

def pack_manifest(target):
    """
    Return the decoded manifest of the action that makes a pack's PCK.

    Godot's export and the writer of a pack without Godot's conversions share the
    manifest's fields of the preset and the content.

    Args:
        target: The pack under test, analyzed with pack_actions.

    Returns:
        The manifest of its GodotPack or GodotPackWrite action as a dict.
    """
    for action in target[PackActionsInfo].actions:
        if action.mnemonic == "FileWrite" and action.outputs.to_list()[0].basename.endswith((".pack.json", ".write.json")):
            return json.decode(action.content)
    fail("%s writes no export manifest" % target.label)
