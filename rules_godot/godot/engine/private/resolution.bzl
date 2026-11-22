"""The engine toolchain types and the diagnostic of a slot without a candidate."""

visibility(["//godot/..."])

EDITOR_TOOLCHAIN_TYPE = Label("//godot:editor_toolchain_type")
RUNTIME_TOOLCHAIN_TYPE = Label("//godot:runtime_toolchain_type")

_SLOTS = {
    "editor": "this execution platform",
    "runtime": "this target platform and Godot variant",
}

def engine_toolchain(ctx, role, slot = None):
    """
    Return the resolved editor or runtime toolchain value, failing with role and reason.

    Declare the type as an optional toolchain (config_common.toolchain_type(...,
    mandatory = False)) so a missing candidate reaches this diagnostic instead of a
    generic resolution error.

    Args:
        ctx: Rule context of the consumer.
        role: "editor" or "runtime".
        slot: What the slot is matched against, for the diagnostic; the execution or target
            platform by default.

    Returns:
        The ToolchainInfo.godot struct of the selected component.
    """
    toolchain = ctx.toolchains[EDITOR_TOOLCHAIN_TYPE if role == "editor" else RUNTIME_TOOLCHAIN_TYPE]
    if not toolchain:
        fail((
            "%s: no registered Godot %s component of the selected engine matches %s. Register " +
            "a registration set that covers the slot, such as a hub's toolchains:all or a " +
            "package of godot_%s_component targets, whose engine is the one " +
            "--@autoload_rules_godot//godot:engine names, empty for the default engine."
        ) % (ctx.label, role, slot or _SLOTS[role], role))
    return toolchain.godot
