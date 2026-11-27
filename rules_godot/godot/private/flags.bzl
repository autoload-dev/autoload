"""Values of rules_godot that rules read like build settings."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")

visibility("//godot/...")

def _value_impl(ctx):
    return [BuildSettingInfo(value = ctx.attr.value)]

bool_value = rule(
    doc = """
    A boolean that rules read through BuildSettingInfo, such as whether Bazel's --stamp
    is set, which a select decides.
    """,
    implementation = _value_impl,
    attrs = {"value": attr.bool(doc = "The value rules read.")},
)
