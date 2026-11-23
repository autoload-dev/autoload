"""The project a pack exports: its view combined with the native code of its platform slices."""

load("//godot/private:actions.bzl", "write_manifest")
load("//godot/private:context.bzl", "TRANSITION_ATTRS", "reset_transition")
load("//godot/private:graph.bzl", "project_graph")
load("//godot/private:operation_addons.bzl", "operation_addons")
load("//godot/private:project.bzl", "NamedAddonsInfo")
load("//godot/private:resources.bzl", "classify", "compose", "extension_file_paths", "unique_extensions", "unique_platform_libraries")
load("//godot/private:view.bzl", "GodotViewInfo", "filter_runtime_extensions")

visibility("//godot/private/...")

GodotPackNativeInfo = provider(
    doc = "What a pack's selection and project deliver in one platform slice: their members, the extensions, platform libraries and Info.plist fragments of their add-ons.",
    fields = [
        "member_resource_paths",
        "export_extensions",
        "platform_libraries",
        "infoplists",
    ],
)

def _native_impl(ctx):
    # The last of deps holds the add-ons the project names.
    named = ctx.attr.deps[-1][NamedAddonsInfo].addons
    direct = classify(ctx.attr.deps[:-1])

    # The pack's view checks the add-ons' directories.
    operation = operation_addons(named, direct.resources, direct.addons)
    composition = compose(str(ctx.label), operation.dependencies, operation.extensions)
    return [GodotPackNativeInfo(
        member_resource_paths = composition.member_resource_paths,
        export_extensions = operation.extensions,
        platform_libraries = unique_platform_libraries([
            library
            for addon in operation.addons
            for library in addon.platform_libraries
        ]),
        infoplists = depset(transitive = [addon.platform_contributions.infoplists for addon in operation.addons]),
    )]

# The pack's path to native code: its selection and the add-ons its project names outside
# every project context, so they import nothing here, in the configuration of the
# platform slice or application reaching it. Its deps are what rules_android's and
# rules_apple's aspects follow to the add-ons' extensions and platform libraries.
godot_pack_native = rule(
    implementation = _native_impl,
    cfg = reset_transition,
    attrs = {
        "deps": attr.label_list(doc = "The pack's selection, then the add-ons its project names."),
    } | TRANSITION_ATTRS,
)

def _add_runtime_files(members, descriptors, name, extension):
    """Add an extension's runtime files of one platform slice; collect its descriptor per platform slice."""
    for path, file in extension.runtime_resource_paths.items():
        if file == extension.runtime_descriptor:
            descriptors.setdefault(path, {})[name] = file
        elif members.setdefault(path, file) != file:
            fail("Extension library conflicts with a member at res://%s" % path)

def _unite_descriptors(ctx, members, descriptors):
    """Add each descriptor as a member; one that platform slices write differently is united."""
    united = {}
    for path, sources in descriptors.items():
        if len(sources) == 1:
            members[path] = sources.values()[0]
            continue
        output = ctx.actions.declare_file(ctx.label.name + "/extensions/" + path)
        members[path] = output
        united[path] = {"output": output.path, "sources": {name: file.path for name, file in sources.items()}}
    if not united:
        return
    manifest = write_manifest(ctx, ".descriptors", {"descriptors": united})
    ctx.actions.run(
        executable = ctx.executable._common_content,
        arguments = ["--manifest", manifest.path],
        inputs = [manifest] + [file for path in united for file in descriptors[path].values()],
        outputs = [members[path] for path in united],
        mnemonic = "GodotExtensionDescriptors",
        progress_message = "Generating %{label}",
    )

def pack_project(ctx):
    """
    Combine the pack's view with the native code of its platform slices.

    The view holds the members and imports, which every platform slice shares; each
    platform slice adds its extension runtime libraries and descriptor.

    Args:
        ctx: Pack rule analysis context with view, native and _common_content.

    Returns:
        A struct of the view and the fields the platform slices change: members,
        their owners, extensions and the graph over them.
    """
    view = ctx.attr.view[GodotViewInfo]
    natives = {name: target[GodotPackNativeInfo] for name, target in ctx.split_attr.native.items()}
    view_extension_paths = extension_file_paths(view.export_extensions)
    members = {
        path: file
        for path, file in view.member_resource_paths.items()
        if path not in view_extension_paths
    }
    descriptors = {}
    export_extensions = []
    for name in sorted(natives):
        export_extensions.extend(natives[name].export_extensions)
        for extension in natives[name].export_extensions:
            _add_runtime_files(members, descriptors, name, extension)
    _unite_descriptors(ctx, members, descriptors)
    owners = dict(view.member_owners)
    for path in members:
        owners.setdefault(path, str(ctx.label))
    graph = project_graph(
        ctx,
        view.runtime_project_file,
        members,
        view.import_resource_paths,
        owners,
        view.import_owners,
        view.relationships,
        ignored = view.ignored_resource_paths,
        index = view.metadata_index,
        extensions = export_extensions,
        # Pack selection reads no diagnostics; the view's graph reports add-on uses.
        addons = [],
        units = [],
    )
    return struct(
        view = view,
        member_resource_paths = members,
        member_owners = owners,
        export_extensions = unique_extensions(export_extensions),
        runtime_extensions = filter_runtime_extensions(export_extensions),
        graph = graph.graph,
        graph_manifest = graph.manifest,
    )
