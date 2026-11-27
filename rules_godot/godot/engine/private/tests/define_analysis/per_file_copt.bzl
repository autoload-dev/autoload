"""A test rule that builds a header in a configuration that sets --per_file_copt."""

visibility("private")

def _per_file_copt_impl(_settings, _attr):
    return {"//command_line_option:per_file_copt": ["godot/engine/private/tests/define_analysis/.*@-DUNRELATED"]}

_per_file_copt = transition(
    implementation = _per_file_copt_impl,
    inputs = [],
    outputs = ["//command_line_option:per_file_copt"],
)

def _header_impl(ctx):
    # A copy of its own, since runfiles key files by their configuration-free path.
    copy = ctx.actions.declare_file(ctx.label.name + ".h")
    ctx.actions.symlink(output = copy, target_file = ctx.file.header)
    return [DefaultInfo(files = depset([copy]))]

header_with_per_file_copt = rule(
    doc = "The header, built with --per_file_copt set.",
    implementation = _header_impl,
    attrs = {"header": attr.label(allow_single_file = True, cfg = _per_file_copt)},
)
