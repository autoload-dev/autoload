"""A signed macOS application built in adhoc signing mode, for tests over its outputs."""

visibility("private")

_MODE = str(Label("//godot:macos_signing"))

def _adhoc_transition_impl(_settings, _attr):
    return {_MODE: "adhoc"}

_adhoc_transition = transition(
    implementation = _adhoc_transition_impl,
    inputs = [],
    outputs = [_MODE],
)

def _adhoc_signed_impl(ctx):
    return [DefaultInfo(files = ctx.attr.app[0][DefaultInfo].files)]

adhoc_signed = rule(
    doc = "The outputs of a godot_macos_sign target built with --//godot:macos_signing=adhoc.",
    implementation = _adhoc_signed_impl,
    attrs = {
        "app": attr.label(mandatory = True, cfg = _adhoc_transition),
    },
)
