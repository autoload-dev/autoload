"""A symbolic macro defined outside its caller package, whose helper the caller can see."""

def _file_impl(ctx):
    output = ctx.actions.declare_file(ctx.label.name + ".txt")
    ctx.actions.write(output, "visibility fixture\n")
    return [DefaultInfo(files = depset([output]))]

_file = rule(implementation = _file_impl)

def _leak_impl(name, visibility, **kwargs):
    _file(name = name, visibility = visibility, **kwargs)
    native.filegroup(name = name + ".unexpected", srcs = [":" + name], visibility = ["//" + native.package_name() + ":__pkg__"])

same_package_leak = macro(
    doc = """
    Produce a controlled file.

    ### Default outputs
    - files (one): build
    """,
    inherit_attrs = "common",
    implementation = _leak_impl,
)
