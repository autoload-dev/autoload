"""Builds one side module per Emscripten version in one invocation, as per-engine builds would."""

_FLAG = "//emscripten:version"

def _version_transition_impl(_settings, attr):
    return {_FLAG: attr.emscripten}

_version_transition = transition(
    implementation = _version_transition_impl,
    inputs = [],
    outputs = [_FLAG],
)

def _impl(ctx):
    src = ctx.file.module
    out = ctx.actions.declare_file("%s/%s" % (ctx.label.name, src.basename))
    ctx.actions.symlink(output = out, target_file = src)
    return [DefaultInfo(files = depset([out]))]

side_module_for = rule(
    implementation = _impl,
    attrs = {
        "emscripten": attr.string(mandatory = True),
        "module": attr.label(allow_single_file = True, cfg = _version_transition),
    },
)
