"""How a pack's PCK is made: Godot's export, or written without Godot's conversions."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")

visibility("//godot/...")

# Rules that make a PCK add this private attribute.
PACK_CONVERSION_ATTRS = {
    "_pack_conversion": attr.label(
        default = Label("//godot:pack_conversion"),
        providers = [BuildSettingInfo],
    ),
}

def pack_conversion(ctx):
    """
    Return how --@autoload_rules_godot//godot:pack_conversion and the compilation mode make a PCK.

    Args:
        ctx: Rule context with PACK_CONVERSION_ATTRS.

    Returns:
        "godot" for Godot's export, "none" for the PCK written without Godot.
    """
    flag = ctx.attr._pack_conversion[BuildSettingInfo].value
    optimized = ctx.var["COMPILATION_MODE"] == "opt"
    if flag == "auto":
        return "godot" if optimized else "none"
    if flag == "none" and optimized:
        fail(
            "--@autoload_rules_godot//godot:pack_conversion=none packs scenes, resources and " +
            "scripts as text, which is for development builds only; drop the flag or " +
            "build without --compilation_mode=opt.",
        )
    return flag
