"""One resource graph per project, shared by pack selection and godot_resource_graph."""

load("//godot/private:metadata.bzl", "metadata_kinds")

visibility("private")

def _file_line(item):
    kind, path, file, owner = item
    return json.encode([kind, path, file.path, owner])

def addon_owners(addon):
    """The owners of an add-on's files: the add-on, and the extensions it brings."""
    return [str(addon.label)] + [str(extension.runtime_descriptor.owner) for extension in addon.extensions]

def _addon_line(addon):
    return json.encode(["addon", str(addon.label), addon_owners(addon)])

def _uses_line(unit):
    # Add-on parts declare no uses; their declaration checks them.
    return json.encode(["uses", unit["owner"], unit["uses"]]) if "uses" in unit else None

def _ignored_line(path):
    return json.encode(["ignored", path])

def _relationship_line(relationship):
    source, target, kind, owner = relationship
    return json.encode(["relationship", source, target, kind, owner])

def project_graph(
        ctx,
        project_file,
        member_resource_paths,
        import_resource_paths,
        member_owners,
        import_owners,
        relationships,
        ignored,
        index,
        extensions,
        addons,
        units):
    """
    Declare the scan of a project's declared files.

    Bazel runs it only when a consumer needs the graph, and the manifest
    expands only then too, so a project without such consumers pays for
    neither.

    Args:
        ctx: Project rule context with a _resource_graph executable.
        project_file: Composed project.godot File.
        member_resource_paths: Member resource paths to Files.
        import_resource_paths: Import input resource paths to Files.
        member_owners: Member resource paths to declaring labels.
        import_owners: Import input resource paths to declaring labels.
        relationships: depset of (source, target, kind, owner) path tuples.
        ignored: Resource paths of the files Godot ignores, which the scan never reads.
        index: The project's metadata index File, or None. Its UIDs identify
            files that only generated sidecars do, and references the build
            corrects from it resolve by path.
        extensions: GodotExtensionInfo of the project's extensions; the scan lists
            their descriptors and extension libraries without reading them, so they
            are no inputs.
        addons: GodotAddonInfo of the operation; a content file referring to one of
            their files while its resources use none of them is reported (FR-026).
            Empty where no consumer reads the graph's diagnostics.
        units: The operation's import units, whose uses name the add-ons each
            resources target may use. They go to a file of their own, so that a
            change of uses reruns the scan and nothing else that reads the manifest.

    Returns:
        A struct with the graph File and the manifest File listing the
        declared files, which also maps each path to its source.
    """
    unread = {
        path: True
        for extension in extensions
        for path in extension.runtime_resource_paths
    }
    lines = ctx.actions.args()
    lines.set_param_file_format("multiline")
    lines.add(json.encode(["project_file", project_file.path]))
    lines.add_all(
        [
            ("member", path, file, member_owners.get(path, ""))
            for path, file in member_resource_paths.items()
        ],
        map_each = _file_line,
    )
    lines.add_all(
        [
            ("import", path, file, import_owners.get(path, ""))
            for path, file in import_resource_paths.items()
        ],
        map_each = _file_line,
    )
    lines.add_all(sorted(ignored), map_each = _ignored_line)
    lines.add_all(relationships, map_each = _relationship_line)
    if index:
        # The build corrects references with assign and sync, not with require.
        corrects = "resource_uids" in metadata_kinds(ctx, ["assign", "sync"])
        lines.add(json.encode(["metadata_index", index.path, corrects]))
    manifest = ctx.actions.declare_file(ctx.label.name + ".graph-manifest.jsonl")
    ctx.actions.write(manifest, lines)
    graph = ctx.actions.declare_file(ctx.label.name + ".graph.json")
    arguments = ["scan", "--manifest", manifest.path, "--output", graph.path]
    scanned = [manifest, project_file] + ([index] if index else [])
    if addons:
        uses = ctx.actions.args()
        uses.set_param_file_format("multiline")
        uses.add_all(addons, map_each = _addon_line)
        uses.add_all(units, map_each = _uses_line)
        addon_manifest = ctx.actions.declare_file(ctx.label.name + ".graph-addons.jsonl")
        ctx.actions.write(addon_manifest, uses)
        arguments += ["--addons", addon_manifest.path]
        scanned.append(addon_manifest)
    ctx.actions.run(
        executable = ctx.executable._resource_graph,
        arguments = arguments,
        inputs = scanned + [
            file
            for path, file in member_resource_paths.items()
            if path not in unread
        ] + import_resource_paths.values(),
        outputs = [graph],
        mnemonic = "GodotResourceGraph",
        progress_message = "Generating %{label}",
    )
    return struct(graph = graph, manifest = manifest)
