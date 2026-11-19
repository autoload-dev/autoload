"""Intentionally incomplete APIs proving that evaluated extraction preserves gaps."""

def _impl(ctx):
    _ = ctx
    return []

def _repo_impl(ctx):
    ctx.file("BUILD.bazel", "")

def _extension_impl(ctx):
    _ = ctx

def _macro_impl(name, visibility, data):
    _ = (name, visibility, data)

_original = rule(implementation = _impl, attrs = {"data": attr.string()})
public_alias = _original

# buildifier: disable=provider-params
UndocumentedInfo = provider(fields = {"payload": ""})
repo = repository_rule(implementation = _repo_impl, attrs = {"url": attr.string()})
extension = module_extension(
    implementation = _extension_impl,
    tag_classes = {"pin": tag_class(attrs = {"version": attr.string()})},
)
symbolic = macro(implementation = _macro_impl, attrs = {"data": attr.string()})
scan = aspect(implementation = _impl, attrs = {"mode": attr.string()})

def tiny(value):
    return value
