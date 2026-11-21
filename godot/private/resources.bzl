"""Godot resources as import units: their composition, staging and import under an operation's project."""

load("//godot/private:actions.bzl", "write_manifest")
load("//godot/private:context.bzl", "TRANSITION_ATTRS", "is_context", "reset_transition")
load("//godot/private:execution.bzl", "EDITOR_TOOLCHAIN")
load(
    "//godot/private:import_units.bzl",
    "GAME_ONLY",
    "VALIDATION_ATTRS",
    "class_fragment",
    "import_unit",
    "unit_interface",
    "validate_unit",
)
load("//godot/private:paths.bzl", "collect_resource_paths", "godot_ignore_markers", "godot_ignored", "mapped_paths", "merge_resource_paths", "sidecar_source", "validate_namespace", "validate_resource_path")
load("//godot/private:providers.bzl", "GodotAddonInfo", "GodotProjectInfo", "GodotResourcesInfo")

visibility(["//godot", "//godot/private/config"])

def unique_extensions(extensions):
    by_descriptor = {}
    for extension in extensions:
        by_descriptor[extension.runtime_descriptor.path] = extension
    return [by_descriptor[path] for path in sorted(by_descriptor)]

def classify(targets):
    """
    Split deps into resources and the add-ons they use.

    Args:
        targets: The deps Targets of a resources target or an operation.

    Returns:
        A struct of GodotResourcesInfo and GodotAddonInfo lists; an extension counts
        as an add-on of only that extension. Anything else fails: platform
        libraries belong to the add-on that needs them.
    """
    resources = []
    addons = []
    for target in targets:
        if GodotResourcesInfo in target:
            resources.append(target[GodotResourcesInfo])
        elif GodotAddonInfo in target:
            addons.append(target[GodotAddonInfo])
        else:
            fail((
                "%s in deps is no godot_resources, godot_addon or extension; declare " +
                "it on a godot_addon, platform libraries in its platform_deps"
            ) % target.label)
    return struct(resources = resources, addons = addons)

def unique_platform_libraries(platform_libraries):
    """
    Remove duplicate platform libraries.

    Args:
        platform_libraries: Platform library Targets, possibly repeated.

    Returns:
        The Targets, each label once, sorted by label.
    """
    by_label = {}
    for target in platform_libraries:
        by_label[target.label] = target
    return [by_label[label] for label in sorted(by_label, key = str)]

def addon_closure(direct, transitive = []):
    """
    The add-ons a use brings: each used add-on after the add-ons it needs.

    Args:
        direct: GodotAddonInfo of the add-ons used directly.
        transitive: Further depsets of GodotAddonInfo, such as GodotResourcesInfo.addons
            of dependencies.

    Returns:
        A postorder depset of GodotAddonInfo, so every add-on comes after those it needs.
    """
    return depset(direct, transitive = [addon.addons for addon in direct] + transitive, order = "postorder")

def _edges(kind, paths, owner):
    return [("", path, kind, owner) for path in sorted(paths)]

def configuration_contributions(values, owner):
    return [(key, value, owner) for key, value in values.items()]

def _merge(destination, resources, owners):
    merge_resource_paths(
        destination,
        resources.member_resource_paths,
        owners = owners,
        additions_owners = resources.member_owners,
    )

def _merge_imports(destination, resources, owners):
    merge_resource_paths(
        destination,
        resources.import_resource_paths,
        owners = owners,
        additions_owners = resources.import_owners,
    )

def _merge_extensions(members, extensions, owners):
    for extension in extensions:
        merge_resource_paths(
            members,
            extension.runtime_resource_paths,
            owners = owners,
            owner = str(extension.runtime_descriptor.owner),
        )

def _source_owner(dependency, sidecar, source):
    """The label declaring source in a dependency that lacks the sidecar, or None."""
    if sidecar in dependency.member_resource_paths or sidecar in dependency.import_resource_paths:
        return None
    return dependency.member_owners.get(source) or dependency.import_owners.get(source)

def _check_sidecar(sidecar, source, dependencies):
    """Fail for a sidecar whose source a dependency declares without it."""
    for dependency in dependencies:
        declared = _source_owner(dependency, sidecar, source)
        if declared:
            fail((
                "Authored sidecar res://%s must be declared in %s with res://%s; " +
                "adding it later would change the cached resource identity or " +
                "import settings"
            ) % (sidecar, declared, source))

def _validate_import_sidecars(selected, dependencies):
    """
    Reject a sidecar that this composition adds to a source a dependency already has.

    The dependency's units imported that source without the sidecar. Each
    dependency passed this check itself, so a sidecar it has is in every one of
    its units that has the source.
    """
    for sidecar in selected:
        source = sidecar_source(sidecar)
        if source:
            _check_sidecar(sidecar, source, dependencies)

def extension_file_paths(extensions):
    return {path: True for extension in extensions for path in extension.runtime_resource_paths}

def import_staged(paths, ignored):
    """The files an import stages: no scripts or scenes, and none of ignored, which Godot ignores."""
    return {
        path: file
        for path, file in paths.items()
        if not path.endswith(GAME_ONLY) and path not in ignored
    }

def _staging(ctx, composition, dependencies):
    """Declare the files imports stage: assets and import inputs, never scripts or scenes."""
    ignored = composition.ignored_resource_paths
    own = import_staged(composition.own, ignored)
    manifests = [write_manifest(ctx, ".resource_paths", mapped_paths(own))] if own else []

    # Import inputs are what an import reads, scripts included, such as a scene import's
    # post-import script; the targets declaring them list only their assets.
    import_inputs = {
        path: file
        for path, file in composition.import_resource_paths.items()
        if path not in composition.member_resource_paths and path not in ignored
    }
    scripts = {path: file for path, file in import_inputs.items() if path.endswith(GAME_ONLY)}
    if scripts:
        manifests.append(write_manifest(ctx, ".import_scripts", mapped_paths(scripts)))
    paths = import_staged(composition.member_resource_paths, ignored) | import_inputs
    return struct(
        resource_path_manifests = depset(
            manifests,
            transitive = [dependency.resource_path_manifests for dependency in dependencies],
        ),
        inputs = depset(paths.values()),
    )

def compose(owner, dependencies, extensions = [], own = {}):
    """
    Merge a target's own files with its dependencies' members and import inputs.

    Args:
        owner: Label string of the composing target.
        dependencies: GodotResourcesInfo of its dependencies.
        extensions: GodotExtensionInfo whose files become members, such as the
            extensions of an operation's add-ons; resources have none.
        own: Its own member resource paths; an operation has none.

    Returns:
        The composition, a struct.
    """
    member_owners = {path: owner for path in own}
    members = dict(own)
    imports = {}
    import_owners = {}

    # Each target decides once which of its own files Godot ignores.
    ignored = {path: own[path] for path in godot_ignored(own)}
    for dependency in dependencies:
        _merge(members, dependency, member_owners)
        _merge_imports(imports, dependency, import_owners)
        ignored.update(dependency.ignored_resource_paths)
    _merge_extensions(members, extensions, member_owners)
    return struct(
        own = own,
        member_resource_paths = members,
        member_owners = member_owners,
        import_resource_paths = imports,
        import_owners = import_owners,
        ignored_resource_paths = ignored,
        extensions = extensions,
    )

def validate_composition(composition, dependencies):
    """
    Check a composition's namespace and the sidecars it adds to its dependencies.

    Args:
        composition: The composition, from compose.
        dependencies: GodotResourcesInfo of the dependencies it composes.
    """
    staged = dict(composition.member_resource_paths)
    staged_owners = dict(composition.member_owners)
    merge_resource_paths(
        staged,
        composition.import_resource_paths,
        owners = staged_owners,
        additions_owners = composition.import_owners,
    )
    validate_namespace(staged, staged_owners)
    _validate_import_sidecars(staged, dependencies)
    _validate_ignored(composition, staged_owners)

def _validate_ignored(composition, owners):
    """
    Reject a file below a directory Godot ignores that another target declares than its marker.

    Each target decides which of its own files Godot ignores, so the .gdignore or
    project.godot that makes Godot skip a directory comes with the files below it, as a
    sidecar comes with its source. Without a marker this costs nothing.
    """
    ignored = composition.ignored_resource_paths
    for marker in godot_ignore_markers(ignored):
        directory = marker.rpartition("/")[0] + "/"
        for path in owners:
            if path.startswith(directory) and path not in ignored:
                fail((
                    "res://%s is in a directory Godot ignores; declare it in %s with " +
                    "res://%s, or move it out of that directory"
                ) % (path, owners[marker], marker))

def dependency_units(dependencies):
    """
    Collect the import units of dependencies and the units they stand for.

    Args:
        dependencies: GodotResourcesInfo of the dependencies.

    Returns:
        The dependencies-first list of units, and the list of unit owner labels
        the dependencies stand for. Each list is dependencies-first; keeping
        first occurrences preserves that.
    """
    units = {}
    heads = {}
    for dependency in dependencies:
        heads.update({head: True for head in dependency.unit_heads})
        for unit in dependency.units:
            if unit["owner"] not in units:
                units[unit["owner"]] = unit
    return list(units.values()), list(heads)

def composition_import_inputs(composition):
    """The import resource paths of a composition that are no members, and their owners."""
    import_inputs = {
        path: file
        for path, file in composition.import_resource_paths.items()
        if path not in composition.member_resource_paths
    }
    return import_inputs, {path: composition.import_owners[path] for path in import_inputs}

def _resources_edges(ctx, composition, owner):
    """
    Merge the import inputs into the composition and list the target's relationship edges.

    Returns:
        The membership, runtime and import edges and the declared runtime references.
    """
    edges = _edges("membership", composition.own, owner)
    for target in ctx.attr.runtime_deps:
        edges.extend(_edges("runtime", target[GodotResourcesInfo].member_resource_paths, owner))
    for target in ctx.attr.import_inputs:
        resources = target[GodotResourcesInfo]
        _merge(composition.import_resource_paths, resources, composition.import_owners)
        _merge_imports(composition.import_resource_paths, resources, composition.import_owners)
        composition.ignored_resource_paths.update(resources.ignored_resource_paths)
        edges.extend(_edges("import", resources.member_resource_paths, owner))
    for source, targets in ctx.attr.runtime_references.items():
        validate_resource_path(source)
        for target in targets:
            validate_resource_path(target)
            edges.append((source, target, "runtime", owner))
    return edges

def _units(composition, dependencies, owner, used):
    """
    The import units of the target and its dependencies, and the units the target stands for.

    The target's own unit lists the add-ons its files may use, which the resource graph checks.
    """
    units, heads = dependency_units(dependencies)
    if not composition.own:
        return units, heads
    units.append({
        "owner": owner,
        "outputs": sorted(composition.own),
        "deps": heads,
        "uses": sorted([str(addon.label) for addon in used]),
    })
    return units, [owner]

def _selection(ctx):
    """
    What the target selects: its dependencies and the add-ons they and its deps use.

    Returns:
        A struct of the direct deps, dependencies (resources and runtime_deps), addons
        (the closure as a depset) and what the target's own unit may use: uses, its
        dependencies and the runtime parts of the add-ons, and their unique extensions
        and autoload contributions.
    """
    direct = classify(ctx.attr.deps)
    dependencies = direct.resources + [target[GodotResourcesInfo] for target in ctx.attr.runtime_deps]
    addons = addon_closure(direct.addons, [dependency.addons for dependency in dependencies])
    used = addons.to_list()
    return struct(
        dependencies = dependencies,
        addons = addons,
        used = used,
        uses = dependencies + [addon.runtime_files for addon in used],
        extensions = unique_extensions([extension for addon in used for extension in addon.extensions]),
        autoloads = [autoload for addon in used for autoload in addon.autoloads],
    )

def _unit_results(ctx, composition, selection, staging):
    """
    Import the target's own unit under its context, with its fragment, interface and validation.

    Returns:
        A struct of imports, the dependencies' import results and the unit's own; its
        class fragments, interface, interfaced paths and validations, none of them
        without a context or own files.
    """
    context = ctx.attr._project[GodotProjectInfo]
    imports = depset(transitive = [dependency.imports for dependency in selection.dependencies])
    if not composition.own or not is_context(context):
        return struct(imports = imports, fragments = [], interface = None, interfaced = [], validations = [])
    unit = struct(suffix = "", owner = str(ctx.label), files = composition.own, ignored = composition.ignored_resource_paths)
    own_import = import_unit(ctx, context, unit, struct(
        resource_path_manifests = staging.resource_path_manifests,
        inputs = staging.inputs,
        imports = imports,
    ))
    fragments = class_fragment(ctx, unit)
    interface = unit_interface(ctx, unit, own_import)

    # The unit may use its dependencies and the runtime parts of the add-ons it uses.
    validations = validate_unit(ctx, context, unit, struct(
        own_import = own_import,
        fragments = fragments,
        uses = selection.uses,
        extensions = selection.extensions,
        autoloads = selection.autoloads,
        runs_in_editor = False,
    ))
    return struct(
        imports = depset([own_import], transitive = [imports]),
        fragments = fragments,
        interface = interface.interface,
        interfaced = interface.interfaced,
        validations = validations,
    )

def _resources_impl(ctx):
    owner = str(ctx.label)
    selection = _selection(ctx)
    dependencies = selection.dependencies
    composition = compose(owner, dependencies, own = collect_resource_paths(ctx))
    edges = _resources_edges(ctx, composition, owner)
    staging = _staging(
        ctx,
        composition,
        dependencies + [target[GodotResourcesInfo] for target in ctx.attr.import_inputs],
    )
    validate_composition(composition, dependencies)
    units, heads = _units(composition, dependencies, owner, selection.used)
    import_inputs, import_owners = composition_import_inputs(composition)
    results = _unit_results(ctx, composition, selection, staging)
    validations = results.validations
    return [DefaultInfo(files = depset(composition.member_resource_paths.values())), OutputGroupInfo(_validation = depset(validations)), GodotResourcesInfo(
        imports = results.imports,
        units = units,
        unit_heads = heads,
        resource_path_manifests = staging.resource_path_manifests,
        member_resource_paths = composition.member_resource_paths,
        import_resource_paths = import_inputs,
        member_owners = composition.member_owners,
        import_owners = import_owners,
        ignored_resource_paths = composition.ignored_resource_paths,
        relationships = depset(edges, transitive = [dependency.relationships for dependency in dependencies]),
        # A use brings the add-on to the operations, never into this import.
        addons = selection.addons,
        class_fragments = depset(results.fragments, transitive = [dependency.class_fragments for dependency in dependencies]),
        interfaces = depset(
            [results.interface] if results.interface else [],
            transitive = [dependency.interfaces for dependency in dependencies],
        ),
        interfaced_resource_paths = depset(
            results.interfaced,
            transitive = [dependency.interfaced_resource_paths for dependency in dependencies],
        ),
        validations = depset(validations, transitive = [dependency.validations for dependency in dependencies]),
    )]

godot_resources = rule(
    doc = """
    Declare Godot resources as one import unit, imported under the project of each
    operation that reaches them.

    Produces GodotResourcesInfo and DefaultInfo. Under the project an operation names,
    the target imports its own files once per project and target platform, after its
    dependencies; outside every operation it imports nothing. deps and runtime_deps
    become members of the operations that reach them, and the add-ons in deps come
    with them; import_inputs are available only during import. Conflicting resource
    paths fail. Under each project, a validation in the _validation output group loads
    the target's own scripts and scenes with what deps bring, and every build containing
    the target fails on the errors Godot reports. Autoloads, settings, extensions and platform libraries are declared on
    the project or a godot_addon, never on resources.

    Example:
    ```starlark
    godot_resources(name = "textures", srcs = glob(["textures/**"]))
    ```

    See [resource composition](../../resources.md) for resource paths, generated
    files, import ordering and runtime reference cycles.

    ### Default outputs
    | kind | cardinality | availability | behavior |
    | --- | --- | --- | --- |
    | files | many | always | build declared resource files; no run behavior |

    ### Output groups
    none

    ### Generated targets
    none

    ### Providers
    | name | role | availability |
    | --- | --- | --- |
    | GodotResourcesInfo | Members, import inputs, imports and the add-ons used, transitively | always |
    """,
    implementation = _resources_impl,
    attrs = {
        "srcs": attr.label_list(
            doc = """
            Source files of these resources; paths are relative to
            strip_prefix.
            """,
            allow_files = True,
            # Files are the same in every context, so generated ones build once.
            cfg = reset_transition,
        ),
        "resource_paths": attr.label_keyed_string_dict(
            doc = """
            Single-file target to explicit resource path; use for
            generated or external files.
            """,
            allow_files = True,
            cfg = reset_transition,
        ),
        "strip_prefix": attr.string(
            doc = """
            Package-relative prefix removed from srcs paths; empty uses the package
            root.
            """,
        ),
        "deps": attr.label_list(
            doc = """
            What these resources use: other godot_resources, which become members
            of the same operations and are imported first, and the add-ons their
            files use, godot_addon, godot_extension and godot_cc_extension targets.
            Every operation containing these resources contains those add-ons with
            their autoloads, settings, extensions and platform libraries; an
            add-on's files are never an input of this import. Platform libraries,
            autoloads, settings and Info.plist fragments belong on a godot_addon.
            """,
        ),
        "prefix": attr.string(
            doc = """
            Project directory the srcs are placed under, after strip_prefix: files in
            `addon/` with `strip_prefix = "addon"` and `prefix = "addons/inventory"`
            appear at `res://addons/inventory/`. Use it for an add-on whose package
            is not laid out as its project directory. Empty places them relative to
            the package or strip_prefix; resource_paths keep their explicit paths.
            """,
        ),
        "runtime_deps": attr.label_list(
            doc = "Like deps, for resources loaded dynamically at runtime.",
            providers = [GodotResourcesInfo],
        ),
        "import_inputs": attr.label_list(
            doc = """
            Files this import reads that are no members of any operation, such as a
            glTF's buffers or a scene import's post-import script; scripts and scenes
            reach an import only this way.
            """,
            providers = [GodotResourcesInfo],
        ),
        "runtime_references": attr.string_list_dict(
            doc = """
            Source path -> runtime destination paths; permits reference cycles without
            Bazel target cycles. A destination that names a directory reaches every
            project member below it.
            """,
        ),
        # The context of the operation that reached these resources; they import
        # under its configuration, and outside every operation not at all.
        "_project": attr.label(
            default = Label("//godot/private:project"),
            providers = [GodotProjectInfo],
        ),
        "_actions": attr.label(
            default = Label("//tools:godot_actions"),
            executable = True,
            cfg = "exec",
        ),
    } | VALIDATION_ATTRS | TRANSITION_ATTRS,
    toolchains = [config_common.toolchain_type(EDITOR_TOOLCHAIN, mandatory = False)],
)

def own_paths(resources):
    """
    The resource paths a resources target stands for, without its dependencies.

    Args:
        resources: GodotResourcesInfo of the target.

    Returns:
        The sorted paths of the target's own unit, or of the units it stands
        for when it declares no files itself.
    """
    heads = {head: True for head in resources.unit_heads}
    return [
        path
        for unit in resources.units
        if unit["owner"] in heads
        for path in unit["outputs"]
    ]
