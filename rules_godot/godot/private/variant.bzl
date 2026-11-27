"""The variant of a build: Godot's release or debug export template, or its editor."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")

visibility("//godot/...")

# Rules that follow the variant add this private attribute.
VARIANT_ATTRS = {
    "_variant": attr.label(
        default = Label("//godot:variant"),
        providers = [BuildSettingInfo],
    ),
}

def variant(ctx):
    """
    Return the variant --@autoload_rules_godot//godot:variant selects.

    Args:
        ctx: Rule context with VARIANT_ATTRS.

    Returns:
        "release", "debug" or "editor".
    """

    # The flag itself rejects other values.
    return ctx.attr._variant[BuildSettingInfo].value
