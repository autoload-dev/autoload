"""Release metadata of packs and applications: explicit values, else build settings."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")

visibility("//godot/...")

# Rules that consume release metadata add these private attributes.
RELEASE_ATTRS = {
    "_app_version": attr.label(
        default = Label("//godot:app_version"),
        providers = [BuildSettingInfo],
    ),
    "_build_number": attr.label(
        default = Label("//godot:build_number"),
        providers = [BuildSettingInfo],
    ),
}

def app_version(ctx, explicit = ""):
    """
    Return the application version a pack or application uses.

    Args:
        ctx: Rule context with RELEASE_ATTRS.
        explicit: The version the target sets itself; empty when unset.

    Returns:
        The explicit version, else --@autoload_rules_godot//godot:app_version, which may be
        empty.
    """
    value = explicit or ctx.attr._app_version[BuildSettingInfo].value
    if value != value.strip() or any([c < " " for c in value.elems()]):
        fail("Application version must not contain whitespace at its ends or control " +
             "characters: %r" % value)
    return value

def build_number(ctx, explicit = 0, default = 0):
    """
    Return the build number an application uses.

    Args:
        ctx: Rule context with RELEASE_ATTRS.
        explicit: The rule's own build number attribute; 0 when unset.
        default: Build number used when neither the attribute nor the build setting
            is set.

    Returns:
        The explicit build number, else --@autoload_rules_godot//godot:build_number, else
        default.
    """
    value = explicit or ctx.attr._build_number[BuildSettingInfo].value or default
    if value < 0:
        fail("Build number must be positive, got %d" % value)
    return value
