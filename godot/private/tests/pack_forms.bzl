"""The form of a pack that tests of Godot's pack export build, and packs in a chosen form."""

load("//godot:providers.bzl", "GodotPackInfo")

visibility("//godot/...")

# Tests of the GodotPack action build the form Godot exports, which --compilation_mode=opt
# selects by default; any other build writes the pack without Godot, which
# pack_conversion_tests.bzl covers.
PACK_CONVERSION = str(Label("//godot:pack_conversion"))
GODOT_EXPORT = {PACK_CONVERSION: "godot"}

def _godot_export_impl(_settings, _attr):
    return GODOT_EXPORT

# The edge of a test rule to a pack it inspects as Godot's export.
godot_export_transition = transition(
    implementation = _godot_export_impl,
    inputs = [],
    outputs = [PACK_CONVERSION],
)

def _pack_form_transition_impl(_settings, attr):
    return {PACK_CONVERSION: attr.form}

_pack_form_transition = transition(
    implementation = _pack_form_transition_impl,
    inputs = [],
    outputs = [PACK_CONVERSION],
)

def _pack_form_impl(ctx):
    pack = ctx.attr.pack[0][GodotPackInfo]

    # The forms' PCKs share their short path; each form's copy has a name of its own.
    named = ctx.actions.declare_file(ctx.label.name + ".pck")
    ctx.actions.symlink(output = named, target_file = pack.pack_file)
    return [pack, DefaultInfo(files = depset([named]))]

pack_form = rule(
    implementation = _pack_form_impl,
    doc = "A pack built in one form, for build-output and run tests of both forms.",
    attrs = {
        "pack": attr.label(mandatory = True, providers = [GodotPackInfo], cfg = _pack_form_transition),
        "form": attr.string(mandatory = True, values = ["godot", "none"]),
    },
)
