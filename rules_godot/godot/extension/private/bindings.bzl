"""
Internal binding-generation contract used by generated godot-cpp repositories.

Consumer BUILD files should use godot/extension:defs.bzl. These exported
names are loadable by consumer-named generated repositories, but are not part
of the public API.
"""

visibility("public")

def _bindings_impl(ctx):
    outputs = [ctx.actions.declare_file(path) for path in ctx.attr.outs]
    args = ctx.actions.args()
    args.add("--generator", ctx.file.generator)
    args.add("--api", ctx.file.api)
    args.add("--interface", ctx.file.interface)
    args.add("--bits", ctx.attr.bits)
    args.add("--precision", ctx.attr.precision)
    args.add("--output-root", outputs[0].path.split("/gen/")[0])
    inputs = [
        ctx.file.generator,
        ctx.file.api,
        ctx.file.interface,
        ctx.file.interface_generator,
    ]
    if ctx.file.profile:
        args.add("--profile", ctx.file.profile)
        args.add("--profile-generator", ctx.file.profile_generator)
        inputs.extend([ctx.file.profile, ctx.file.profile_generator])
    ctx.actions.run(
        executable = ctx.executable._tool,
        inputs = inputs,
        outputs = outputs,
        arguments = [args],
        mnemonic = "GodotCppBindings",
        progress_message = "Generating %{label}",
    )
    headers = [f for f in outputs if f.extension != "cpp"]
    sources = [f for f in outputs if f.extension == "cpp"]
    return [
        DefaultInfo(files = depset(outputs)),
        OutputGroupInfo(headers = depset(headers), sources = depset(sources)),
    ]

godot_cpp_bindings = rule(
    doc = """
    Generate the explicitly declared godot-cpp binding sources and headers.

    This low-level build rule is instantiated by the BUILD file the godot_cpp_bindings
    repository rule generates. DefaultInfo
    contains all outs; OutputGroupInfo.headers and .sources separate the outputs
    for downstream C++ compilation. A profile requires profile_generator.
    See [the generated godot-cpp repository](../../gdextension.md) for the normal
    consumer API and a complete C++ example.
    """,
    implementation = _bindings_impl,
    attrs = {
        "generator": attr.label(
            doc = "Upstream godot-cpp binding_generator.py file.",
            allow_single_file = True,
            mandatory = True,
        ),
        "api": attr.label(
            doc = "Godot extension API JSON file matching the engine API.",
            allow_single_file = True,
            mandatory = True,
        ),
        "interface": attr.label(
            doc = "Upstream gdextension_interface.h input.",
            allow_single_file = True,
            mandatory = True,
        ),
        "interface_generator": attr.label(
            doc = "Upstream generator for the GDExtension interface bindings.",
            allow_single_file = True,
            mandatory = True,
        ),
        "profile": attr.label(
            doc = "Optional JSON build profile restricting generated classes.",
            allow_single_file = True,
        ),
        "profile_generator": attr.label(
            doc = "Upstream build-profile helper required when profile is supplied.",
            allow_single_file = True,
        ),
        "outs": attr.string_list(
            doc = """
            Exact generated source and header paths; headers and sources are exposed as
            separate output groups.
            """,
            mandatory = True,
        ),
        "bits": attr.string(
            doc = "Pointer width of the generated bindings, 32 or 64.",
            default = "64",
            values = ["32", "64"],
        ),
        "precision": attr.string(
            doc = """
            Floating-point precision, single or double; must match the engine build.
            """,
            default = "single",
            values = ["single", "double"],
        ),
        "_tool": attr.label(
            default = "//tools/extension:bindings",
            executable = True,
            cfg = "exec",
        ),
    },
)
