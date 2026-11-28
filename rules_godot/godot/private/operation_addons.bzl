"""The add-ons of an operation: their order, the files they declare, their editor parts and importers."""

load("//godot/private:graph.bzl", "addon_owners")
load("//godot/private:import_units.bzl", "importer_staging")
load("//godot/private:providers.bzl", "GodotAddonInfo", "GodotResourcesInfo")
load("//godot/private:resources.bzl", "addon_closure", "unique_extensions")

visibility("//godot/private/...")

def _dependencies_first(by_label):
    """Add-ons by label string, each after the add-ons it needs, ties by label."""
    placed = {}
    ordered = []
    for label in sorted(by_label):
        for each in by_label[label].addons.to_list() + [by_label[label]]:
            key = str(each.label)
            if key not in placed:
                placed[key] = True
                ordered.append(by_label[key])
    return ordered

def operation_addons(named, resources, addons):
    """
    The add-ons of an operation: those its selection uses, those they need and those its project names.

    Args:
        named: depset of GodotAddonInfo of the add-ons the project names, NamedAddonsInfo.addons.
        resources: GodotResourcesInfo of the selection's resources.
        addons: GodotAddonInfo of the add-ons the selection names directly.

    Returns:
        A struct of addons, the GodotAddonInfo list, dependencies first, ties by label;
        dependencies, the selection's resources and the add-ons' runtime parts, which
        are members like resources; and extensions, the add-ons' extensions, unique.
    """
    by_label = {}
    for addon in addon_closure(addons, [dependency.addons for dependency in resources] + [named]).to_list():
        by_label.setdefault(str(addon.label), addon)
    ordered = _dependencies_first(by_label)
    return struct(
        addons = ordered,
        dependencies = resources + [addon.runtime_files for addon in ordered],
        extensions = unique_extensions([extension for addon in ordered for extension in addon.extensions]),
    )

def validate_addon_directories(addons):
    """
    Fail for two add-ons of an operation whose directories overlap.

    Args:
        addons: GodotAddonInfo of the operation.
    """

    # With a trailing slash, a directory sorts right before the directories below it.
    claiming = sorted([addon for addon in addons if addon.directory], key = lambda addon: addon.directory + "/")
    for first, second in zip(claiming, claiming[1:]):
        if (second.directory + "/").startswith(first.directory + "/"):
            fail("Add-ons %s (res://%s/) and %s (res://%s/) have overlapping directories" % (
                first.label,
                first.directory,
                second.label,
                second.directory,
            ))

def _enclosing_addons(path, by_directory):
    """The add-ons whose directory holds the resource path, outermost first."""
    parts = path.split("/")
    directories = ["/".join(parts[:depth]) for depth in range(1, len(parts))]
    return [by_directory[directory] for directory in directories if directory in by_directory]

def validate_addon_files(addons, members, owners):
    """
    Fail for a member or import input in an add-on's directory that the add-on does not declare (FR-012).

    Files below an add-on's directory belong to its parts and extensions; resources holding
    a copy of one, such as an editor-part script a test loads, would give one res:// path
    two meanings.

    Args:
        addons: GodotAddonInfo of the operation.
        members: The resource paths of the operation's members or import inputs.
        owners: Those resource paths to the label strings declaring them.
    """
    by_directory = {addon.directory: addon for addon in addons if addon.directory}
    if not by_directory:
        return
    for path in members:
        for addon in _enclosing_addons(path, by_directory):
            # The add-on's parts and extensions declare its files; any other target
            # declaring one, even with the same source, declares it twice.
            if owners.get(path) not in addon_owners(addon):
                fail("res://%s of %s lies in the directory res://%s/ of the add-on %s; declare it in the add-on" % (
                    path,
                    owners.get(path, "the operation"),
                    addon.directory,
                    addon.label,
                ))

def addon_editor_parts(addons, members):
    """
    Collect the editor parts of an operation's add-ons, which its editor views load.

    Args:
        addons: GodotAddonInfo of the operation.
        members: The operation's member resource paths, which an editor part may not reuse.

    Returns:
        A struct of resource_paths, the parts' files, imports, their import results, and
        plugins, the res:// paths of their plugin.cfg files.
    """
    resource_paths = {}
    for addon in addons:
        for path, file in addon.editor_files.member_resource_paths.items():
            if members.get(path, file) != file:
                fail("Editor part file res://%s of %s conflicts with a member" % (path, addon.label))
            resource_paths[path] = file
    return struct(
        resource_paths = resource_paths,
        imports = depset(transitive = [addon.editor_files.imports for addon in addons]),
        plugins = ["res://" + addon.plugin_config for addon in addons if addon.plugin_config],
    )

def _used_addons(target):
    """The label strings of the add-ons a dep of the view uses: its own and those it needs."""
    if GodotResourcesInfo in target:
        used = target[GodotResourcesInfo].addons.to_list()
    else:
        used = [target[GodotAddonInfo]] + target[GodotAddonInfo].addons.to_list()
    return [str(each.label) for each in used]

def require_named_importers(ctx, addons, named):
    """
    Fail for an add-on with an importer role that the operation contains but its project does not name (FR-016).

    Args:
        ctx: Analysis context of the view.
        addons: GodotAddonInfo of the operation.
        named: Label strings of the add-ons the project names.
    """
    for addon in addons:
        label = str(addon.label)
        if not addon.importer_suffixes or label in named:
            continue
        users = [str(target.label) for target in ctx.attr.deps if label in _used_addons(target)]
        fail((
            "%s uses the add-on %s, whose importer role only the project can activate: " +
            "name it in the project's deps of %s"
        ) % (", ".join(users), label, ctx.attr.project.label))

def staged_importers(project, importers):
    """
    What a view's initialization or pack export stages to run importers of the add-ons the project names.

    Args:
        project: GodotProjectInfo of the context.
        importers: GodotAddonInfo, in the operation's context, of the importers that run.

    Returns:
        A struct of resource_paths, what they need to run;
        imports, the import results of their editor parts and of the editor parts of the
        add-ons they need; plugins, their plugin.cfg res:// paths; and settings, the import
        settings they read.
    """
    staging = importer_staging(project, importers)
    return struct(
        resource_paths = staging.resource_paths,
        imports = depset(transitive = [
            each.editor_files.imports
            for addon in importers
            for each in addon.addons.to_list() + [addon]
        ]),
        plugins = staging.plugins,
        settings = staging.settings,
    )
