"""Optional static resource diagnostics without adding build-time dependencies."""

load("//godot/engine/private:selection.bzl", "ENGINE_ATTRS", "engine_transition")
load("//godot/private:view.bzl", "GodotViewInfo", "declare_view")

visibility(["//godot/..."])

def _resource_graph_impl(ctx):
    project = ctx.attr.view[GodotViewInfo]
    graph = ctx.actions.declare_file(ctx.label.name + ".graph.json")
    arguments = ["check", "--graph", project.graph.path, "--output", graph.path]
    if ctx.attr.require_declared:
        arguments.append("--require-declared")
    if ctx.attr.validate:
        arguments.append("--validate")
    ctx.actions.run(
        executable = ctx.executable._scanner,
        arguments = arguments,
        inputs = [project.graph],
        outputs = [graph],
        mnemonic = "GodotResourceGraphCheck",
        progress_message = "Validating %{label}",
    )
    return [DefaultInfo(files = depset([graph]))]

_resource_graph = rule(
    doc = "Check a view's resource graph; the rule behind godot_resource_graph.",
    implementation = _resource_graph_impl,
    attrs = {
        "view": attr.label(
            doc = "The view whose graph is checked.",
            mandatory = True,
            providers = [GodotViewInfo],
        ),
        "validate": attr.bool(
            doc = """
            Fail on missing static references, invalid UID ownership or conflicting
            identities. Dynamic references remain warnings.
            """,
            default = True,
        ),
        "require_declared": attr.bool(
            doc = """
            Require inferred runtime file references to have matching runtime_references
            entries. Project configuration references are implicit; import inputs are
            checked for availability.
            """,
        ),
        "_scanner": attr.label(
            default = Label("//tools:resource_graph"),
            executable = True,
            cfg = "exec",
        ),
    } | ENGINE_ATTRS,
    cfg = engine_transition,
)

def _resource_graph_macro_impl(name, visibility, project, deps, **kwargs):
    _resource_graph(
        name = name,
        visibility = visibility,
        view = declare_view(name, project, deps, kwargs, engine = kwargs.get("engine")),
        **kwargs
    )

godot_resource_graph = macro(
    doc = """
    Emit a deterministic file/UID graph for resources; optionally validate references.

    Does not execute Godot or modify Bazel dependencies.

    Produces a .graph.json file in DefaultInfo from the resource graph of deps under the
    project's configuration, without running Godot or adding inferred Bazel
    dependencies. validate controls failures for invalid static references;
    require_declared additionally requires explicit runtime reference declarations.
    Dynamic references remain warnings.

    Example:
    ```starlark
    godot_resource_graph(
        name = "graph",
        project = ":project",
        deps = [":game"],
        require_declared = True,
    )
    ```

    See [detected references](../../resources.md#detected-references).
    """,
    implementation = _resource_graph_macro_impl,
    inherit_attrs = _resource_graph,
    attrs = {
        "view": None,
        "project": attr.label(
            doc = "The godot_project whose configuration the graph reads.",
            mandatory = True,
            configurable = False,
        ),
        "deps": attr.label_list(doc = "The godot_resources whose files the graph scans."),
    },
)
