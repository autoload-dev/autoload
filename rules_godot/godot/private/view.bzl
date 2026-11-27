"""The view an operation runs Godot on: its project's configuration over the resources it names."""

load("//godot/private:actions.bzl", "run_editor_action", "write_manifest")
load("//godot/private:configuration.bzl", "merge_configuration")
load("//godot/private:context.bzl", "context_transition")
load("//godot/private:execution.bzl", "EDITOR_TOOLCHAIN")
load("//godot/private:graph.bzl", "project_graph")
load("//godot/private:import_units.bzl", "importers_of")
load("//godot/private:macros.bzl", "CALLER_PACKAGE", "common_kwargs")
load("//godot/private:metadata.bzl", "METADATA_ATTRS", "metadata_kinds")
load(
    "//godot/private:operation_addons.bzl",
    "addon_editor_parts",
    "operation_addons",
    "require_named_importers",
    "staged_importers",
    "validate_addon_directories",
    "validate_addon_files",
)
load("//godot/private:paths.bzl", "declared_path", "exec_paths", "resolve_project_path", "with_extensions_for")
load("//godot/private:project.bzl", "NamedAddonsInfo", "configuration_file", "configuration_kinds", "left_out_entries", "named_addons_label")
load("//godot/private:providers.bzl", "GodotProjectInfo")
load("//godot/private:resources.bzl", "classify", "compose", "composition_import_inputs", "configuration_contributions", "dependency_units", "extension_file_paths", "validate_composition")
load("//godot/private:setting_values.bzl", "named_paths", "names_directories", "override_applies", "setting_kind")
load("//godot/private/config:settings.bzl", "entry_features")

visibility([
    "//godot",
    "//godot/engine/private/tests/...",
    "//godot/extension/tests/...",
    "//godot/platforms/private/tests/...",
    "//godot/private/config/tests/...",
    "//godot/private/tests/...",
])

GodotViewInfo = provider(
    doc = """The project one operation runs Godot on: its project's configuration over the resources it names. Produced by _godot_view; read by the operation's own rules.""",
    fields = {
        "project": "GodotProjectInfo of the context",
        "runtime_project_file": "project.godot File of the runtime purpose, which source runs start from",
        "addons": "list of GodotAddonInfo of the operation's add-ons: those its selection uses, those they need and those its project names, dependencies first",
        "editor_resource_paths": "dict of resource paths to the Files the editor stages: members, import inputs and every add-on's editor part, with each extension's editor descriptor and extension editor libraries in place of its runtime ones",
        "editor_imports": "depset[File] of the import results an editor view stages: imports and those of every add-on's editor part",
        "importer_resource_paths": "dict of resource paths to the Files of the importers that convert files of the view, of the add-ons its project names, which its initialization and pack exports stage: their parts, those of the add-ons they need and their extensions' editor files",
        "importer_imports": "depset[File] of the import results of those importers' editor parts",
        "export_configuration": "dict of resolved setting/autoload literals, main scene, and the plugin paths of the importers the export enables (importer_plugins)",
        "export_project_file": "project.godot File that packs export: the runtime configuration with the plugins of the importers that convert its files enabled",
        "shell_project_file": "project.godot File of the shell-assets probe: the export configuration without autoloads, main scene and content-bound settings",
        "editor_project_file": "project.godot File that editor views open: the runtime configuration with the editor plugin of every add-on enabled",
        "composed_settings": "dict[string, string] of the settings the view sets over its authored project.godot, as section/property keys including autoload/<name> and application/run/main_scene, to the label string declaring each",
        "member_resource_paths": "dict of resource paths to the Files of the members",
        "imports": "depset[File] of the import results of the members' units under the project's context",
        "initialized": "File: tree artifact of Godot editor state over the members, built for source runs and editor views",
        "metadata": "JSON File listing what godot_metadata_sync writes into the checkout; built only when a consumer needs it",
        "metadata_index": "JSON File of the metadata the members' text files lack; None when every //godot/metadata flag is off",
        "export_extensions": "list of all GodotExtensionInfo of the operation, which pack exports load and packs list for the runtime",
        "runtime_extensions": "list of GodotExtensionInfo of the extensions the runtime loads",
        "missing_entries": "list of (setting key, first missing path) string pairs of the autoloads, the main scene and the content-bound settings that the view left out because its members lack a file they name",
        "member_owners": "dict[string, string] of the members' resource paths to the label strings declaring them",
        "relationships": "depset of (source, target, kind, owner) string tuples",
        "import_resource_paths": "dict of resource paths to the Files of the import inputs",
        "import_owners": "dict[string, string] of the import inputs' resource paths to the label strings declaring them",
        "ignored_resource_paths": "dict of the resource paths of the members and import inputs Godot ignores to their Files, as GodotResourcesInfo.ignored_resource_paths",
        "graph": "JSON File: the resource graph of the declared files, built only when a consumer needs it",
        "graph_manifest": "JSON-lines File: the project file, members, import inputs and relationships that graph scans",
    },
)

def filter_runtime_extensions(extensions):
    """
    Return the extensions the runtime loads: those with a library in this configuration.

    Args:
        extensions: GodotExtensionInfo of a project's extensions.

    Returns:
        The extensions to deliver to the runtime; one without a library loads nothing at
        runtime.
    """
    return [extension for extension in extensions if extension.library]

def _editor_resource_paths(composition):
    return with_extensions_for(
        composition.member_resource_paths | composition.import_resource_paths,
        composition.extensions,
        "editor",
    )

def _in_checkout(file):
    """Whether a file is a source of the main repository, which the checkout holds."""
    return file.is_source and not file.owner.repo_name

# The files the metadata index reads, besides the import results.
_METADATA_SOURCES = (".tscn", ".tres", ".uid", ".import")
_MAIN_SCENE = "application/run/main_scene"

def _metadata_index(ctx, files):
    """
    Index the metadata the project's text files lack, unless every metadata flag is off.

    The index reads the project's text resources, .uid and .import files and
    the import results, not the initialization, so script edits leave it and
    the packs that read it current.

    Args:
        ctx: Project rule analysis context.
        files: The view's files, as _collect_files collects them.

    Returns:
        The JSON File tools/resources/index.py writes, or None.
    """
    if not metadata_kinds(ctx, ["assign", "sync", "require"]):
        return None
    ignored = files.ignored
    sources = {
        path: file
        for path, file in files.combined.items()
        if path.endswith(_METADATA_SOURCES) and path not in ignored
    }
    out = ctx.actions.declare_file(ctx.label.name + ".metadata_index.json")
    manifest = write_manifest(ctx, ".metadata_index.config", {
        "files": exec_paths(sources),
        "members": sorted([path for path in files.combined if path not in ignored]),
    })
    arguments = ctx.actions.args()
    arguments.add_all(["index", "--manifest", manifest, "--output", out])

    # Import results stay unexpanded and the depset unflattened until execution.
    arguments.add_all(files.imports, before_each = "--import", expand_directories = False)
    ctx.actions.run(
        executable = ctx.executable._metadata_index,
        arguments = [arguments],
        inputs = depset([manifest] + sources.values(), transitive = [files.imports]),
        outputs = [out],
        mnemonic = "GodotMetadataIndex",
        progress_message = "Generating %{label}",
    )
    return out

def _metadata_list(ctx, files, initialized, index):
    """
    List what godot_metadata_sync writes into the checkout.

    That is the sidecars the build generated for checkout files that declare
    none and, for metadata flags at sync or require, the checkout text files
    the metadata index names.

    Args:
        ctx: Project rule analysis context.
        files: The view's files, as _collect_files collects them.
        initialized: The project's initialization.
        index: The project's metadata index, or None.

    Returns:
        The JSON File the action writes; tools/checkout/metadata_sync.py reads it.
    """
    out = ctx.actions.declare_file(ctx.label.name + ".metadata.json")
    checkout = {path: file for path, file in files.combined.items() if _in_checkout(file)}
    manifest = write_manifest(ctx, ".metadata.config", {
        "checkout": {path: [file.path, files.owners[path]] for path, file in checkout.items()},
    })
    arguments = ctx.actions.args()
    arguments.add_all(["list", "--manifest", manifest, "--output", out])
    arguments.add("--initialized", initialized.path)
    arguments.add_all(files.imports, before_each = "--import", expand_directories = False)
    written = metadata_kinds(ctx, ["sync", "require"])
    arguments.add_all(written, before_each = "--update")
    if written:
        arguments.add("--index", index)
    ctx.actions.run(
        executable = ctx.executable._metadata_sync,
        arguments = [arguments],
        inputs = depset([manifest, initialized] + ([index] if written else []), transitive = [files.imports]),
        outputs = [out],
        mnemonic = "GodotMetadata",
        progress_message = "Generating %{label}",
    )
    return out

def _resolve(contributions, overrides, owner):
    """
    Merge contributions in their order; consumer overrides replace conflicting values.

    Returns:
        The merged values and the label string declaring each of them.
    """
    values = {}
    origins = {}
    for key, value, contributor in contributions:
        merge_configuration(values, {key: value}, origins, contributor, overrides)
    values.update(overrides)
    origins.update({key: owner for key in overrides})
    return values, origins

def _context_path(members, path, directory):
    """
    Resolve a file, or with directory also a directory, the context names against an operation's members.

    A directory resolves when the operation's resources hold a file below it (FR-032).

    Returns:
        The resource path, or None when the operation's resources lack it, which
        then leaves the entry out.
    """
    resolved = resolve_project_path(members, path)
    if not resolved:
        return None
    if resolved.kind != "file" and not directory:
        return None
    return resolved.path

def _entry_kind(key):
    """How a failure names an entry: Autoload <name>, Main scene or Setting <key>."""
    if key.startswith("autoload/"):
        return "Autoload " + key.removeprefix("autoload/")
    if key == _MAIN_SCENE:
        return "Main scene"
    return "Setting " + key

def _content_bound(kind):
    """Whether a setting kind, or None for another setting of Godot, names game content."""
    return kind != None and kind["binding"] == "content"

def _names_program_file(key):
    """Whether an entry is an autoload or the main scene, whose files the program loads."""
    return key == _MAIN_SCENE or key.startswith("autoload/")

def _resolve_entries(entries, members, kinds):
    """
    Resolve the files the content-bound entries name against an operation's members.

    A uid:// reference, or any value other than a res:// path, stays: analysis cannot
    resolve it.

    Args:
        entries: Dict of setting key to Godot literal, in the order failures report
            them: the autoloads as autoload/<name>, the main scene as
            application/run/main_scene and the settings.
        members: The view's member resource paths.
        kinds: The setting kinds and sections of the engine version, from configuration_kinds.

    Returns:
        A struct with `paths`, a dict from each kept content-bound autoload and the main
        scene to the resource paths they name, `left_out`, a dict whose keys are the entries left out,
        and `missing_entries`, their (key, path) pairs as GodotViewInfo.missing_entries
        lists them.
    """
    paths = {}
    left_out = {}
    missing_entries = []
    for key, literal in entries.items():
        kind = setting_kind(kinds, key)
        if not _content_bound(kind):
            continue
        named = [path for path in named_paths(kind["shape"], literal) if path.startswith("res://")]
        resolved = [_context_path(members, path, names_directories(kind)) for path in named]
        missing = [path for path, member in zip(named, resolved) if not member]
        if missing:
            left_out[key] = True
            missing_entries.append((key, missing[0]))
        elif _names_program_file(key):
            paths[key] = resolved
    return struct(paths = paths, left_out = left_out, missing_entries = missing_entries)

def _check_flag_settings(flag_settings, setting_origins):
    """
    Fail for a contributed setting that conflicts with a setting of settings_from_flags.

    The same key would have two values, and a feature override of it would hide the
    flag's value where its tag applies.

    Args:
        flag_settings: The settings settings_from_flags sets.
        setting_origins: The contributed setting keys to the labels declaring them.
    """
    bases = {key.split(".")[0]: key for key in flag_settings}
    for key, origin in setting_origins.items():
        flag_key = bases.get(key.split(".")[0])
        if flag_key:
            fail("%s sets %s, which conflicts with %s from settings_from_flags" % (origin, key, flag_key))

def require_entries(view):
    """
    Fail for a declared entry the view left out because its members lack a file it names.

    Entries are the autoloads, the main scene and the content-bound settings. Program
    entries, the operations that start the game themselves, a source run and a pack
    without required packs, call it. The values of the authored project.godot are known
    only when its configuration is constructed: the view of a source run, declared with
    its program_entry, fails for those itself, and a pack checks them in a validation
    action, since only the pack sees its resolved required_packs.

    Args:
        view: GodotViewInfo of the operation. An override with no tag the program entry
            can have, the project's custom features or a tag Godot sets, never applies
            there and needs no file.
    """
    features = entry_features(view.project.custom_features)
    for key, path in view.missing_entries:
        if override_applies(key, features):
            declared_path(view.member_resource_paths, path, _entry_kind(key))

def _compose_selection(ctx):
    """
    Compose the operation's add-ons and resources, and validate what they declare.

    Returns:
        A struct of the operation's addons, dependencies and composition.
    """
    named = ctx.attr.named_addons[NamedAddonsInfo].addons
    direct = classify(ctx.attr.deps)
    used = operation_addons(named, direct.resources, direct.addons)
    validate_addon_directories(used.addons)
    require_named_importers(ctx, used.addons, {str(addon.label): True for addon in named.to_list()})
    composition = compose(str(ctx.label), used.dependencies, used.extensions)
    validate_addon_files(used.addons, composition.member_resource_paths, composition.member_owners)
    return struct(
        addons = used.addons,
        dependencies = used.dependencies,
        composition = composition,
    )

def _merge_contributions(addons, project):
    """
    Merge the operation's settings and autoloads in the add-ons' dependency order, the project's last.

    Returns:
        A struct of settings and autoloads, each with its origins, the label strings
        declaring them.
    """
    project_owner = str(project.label)
    settings, setting_origins = _resolve(
        [setting for addon in addons for setting in addon.settings] +
        configuration_contributions(project.settings, project_owner),
        project.setting_overrides,
        project_owner,
    )
    autoloads, autoload_origins = _resolve(
        [autoload for addon in addons for autoload in addon.autoloads] +
        configuration_contributions(project.autoloads, project_owner),
        project.autoload_overrides,
        project_owner,
    )
    return struct(
        settings = settings,
        setting_origins = setting_origins,
        autoloads = autoloads,
        autoload_origins = autoload_origins,
    )

def _add_context_files(project, composition, owner):
    """Add the project's context files to the members, which must not hold others at their paths."""
    members = composition.member_resource_paths
    for path, file in project.context_files.items():
        if members.get(path, file) != file:
            fail("Context file res://%s conflicts with a member of %s" % (path, owner))
        members[path] = file
        composition.member_owners[path] = str(project.label)

def _main_scene_path(project):
    """The res:// path of the project's main_scene."""
    return "res://" + project.main_scene.removeprefix("res://")

def _entries(project, contributions):
    """The entries whose files resolve against the members: autoloads, main scene and settings."""
    entries = {"autoload/" + name: json.encode(value) for name, value in contributions.autoloads.items()}
    if project.main_scene:
        entries[_MAIN_SCENE] = json.encode(_main_scene_path(project))

    # godot_project.main_scene and the autoloads win over settings of the same key.
    settings = contributions.settings
    entries.update({key: settings[key] for key in sorted(settings) if key not in entries})
    return entries

def _main_scene(project, resolution):
    """The view's main scene: the resolved entry, else the project's unless left out."""
    if _MAIN_SCENE in resolution.paths:
        return "res://" + resolution.paths[_MAIN_SCENE][0]
    if project.main_scene and _MAIN_SCENE not in resolution.left_out:
        return _main_scene_path(project)
    return ""

def _without(values, left_out):
    """Values without the left-out keys; values itself when the view leaves nothing out."""
    if not left_out:
        return values
    return {key: value for key, value in values.items() if key not in left_out}

def _configuration(ctx, project, contributions, members):
    """
    The view's configuration: the contributions without the entries whose files the members lack.

    Returns:
        A struct of settings and autoloads with their origins, main_scene, missing_entries
        as GodotViewInfo lists them, and the base project.godot, kinds and left_out
        entries every configuration_file of the view takes.
    """
    kinds = configuration_kinds(ctx)
    resolution = _resolve_entries(_entries(project, contributions), members, kinds)
    return struct(
        settings = _without(contributions.settings, resolution.left_out),
        setting_origins = _without(contributions.setting_origins, resolution.left_out),
        autoloads = {
            name: value
            for name, value in contributions.autoloads.items()
            if "autoload/" + name not in resolution.left_out
        },
        autoload_origins = contributions.autoload_origins,
        main_scene = _main_scene(project, resolution),
        missing_entries = resolution.missing_entries,
        base = project.authored_project_file,
        kinds = kinds,
        left_out = left_out_entries(ctx, project, members, ctx.attr.program_entry.removeprefix("@@")),
    )

def _configuration_file(ctx, configuration, suffix, **kwargs):
    """The project.godot of the view's configuration for one purpose."""
    return configuration_file(
        ctx,
        configuration.base,
        suffix,
        configuration.settings,
        configuration.autoloads,
        configuration.main_scene,
        kinds = configuration.kinds,
        left_out = configuration.left_out,
        **kwargs
    )

def _composed_settings(configuration, project_owner):
    """The settings the view sets over its authored project.godot, to the labels declaring them."""
    composed = dict(configuration.setting_origins)
    composed.update({
        "autoload/" + name: configuration.autoload_origins[name]
        for name in configuration.autoloads
    })
    if configuration.main_scene:
        composed[_MAIN_SCENE] = project_owner
    return composed

def _collect_files(project, selection):
    """
    Validate the composition and collect the view's files, editor parts and importers.

    Returns:
        A struct of the view's import inputs with their owners, combined with the members
        and with all owners; its imports, units, extensions and ignored files; the
        editor_parts of its add-ons; and the importers that convert its files.
    """
    composition = selection.composition
    addons = selection.addons
    validate_composition(composition, selection.dependencies)
    units, _ = dependency_units(selection.dependencies)
    members = composition.member_resource_paths
    editor_parts = addon_editor_parts(addons, members)
    import_resource_paths, import_owners = composition_import_inputs(composition)
    validate_addon_files(addons, import_resource_paths, import_owners)
    combined = members | import_resource_paths

    # The initialization and the export scan the view's files, so they stage the importers
    # that convert them; without them Godot skips those files.
    # The index holds the add-ons outside every context; their files are the same, and the
    # operation's own carry the import results of its context.
    by_label = {str(addon.label): addon for addon in addons}
    importers = staged_importers(project, [by_label[str(addon.label)] for addon in importers_of(project, combined)])
    return struct(
        import_resource_paths = import_resource_paths,
        import_owners = import_owners,
        combined = combined,
        owners = composition.member_owners | import_owners,
        imports = depset(transitive = [dependency.imports for dependency in selection.dependencies]),
        units = units,
        extensions = composition.extensions,
        ignored = composition.ignored_resource_paths,
        editor_parts = editor_parts,
        importers = importers,
    )

def _purpose_project_files(ctx, configuration, files):
    """The project.godot files of the view's export, shell-assets probe and editor views."""
    return struct(
        # The export enables only the importers that convert the pack's files; it runs no
        # add-on's export plugin (D29).
        export = _configuration_file(
            ctx,
            configuration,
            ".export",
            purpose = "export",
            editor_plugins = files.importers.plugins,
        ),
        # The shell-assets probe stages no game: its configuration carries the export's
        # settings without those that name a file of the game, so it names no autoload, main
        # scene or other file of the game, and enables no plugin.
        shell = configuration_file(
            ctx,
            configuration.base,
            ".shell",
            configuration.settings,
            purpose = "export",
            kinds = configuration.kinds,
            context_only = True,
        ),
        editor = _configuration_file(
            ctx,
            configuration,
            ".editor",
            purpose = "editor",
            editor_plugins = files.editor_parts.plugins,
        ),
    )

def _initialize(ctx, project, files):
    """
    Initialize Godot's editor state over the view's files, with the importers that convert them.

    Initialization loads no extension: its caches are the same without, and an extension's
    editor code could rewrite the configuration.
    """
    initialized = ctx.actions.declare_directory(ctx.label.name + ".initialized")
    extension_paths = extension_file_paths(files.extensions)
    initializing = {
        path: file
        for path, file in files.combined.items()
        if path not in extension_paths
    }
    initializing.update(files.importers.resource_paths)
    run_editor_action(
        ctx,
        "initialize",
        ".initialize",
        initialized,
        {
            "project_file": project.import_configuration.path,
            "member_resource_paths": exec_paths(initializing),
            "editor_plugins": files.importers.plugins,
            "settings": files.importers.settings,
        },
        depset([project.import_configuration] + initializing.values()),
        depset(transitive = [files.imports, files.importers.imports]),
        "GodotInitialize",
        "Initializing %{label}",
    )
    return initialized

def _view_impl(ctx):
    project = ctx.attr.project[GodotProjectInfo]
    selection = _compose_selection(ctx)
    composition = selection.composition
    contributions = _merge_contributions(selection.addons, project)
    _add_context_files(project, composition, str(ctx.label))
    _check_flag_settings(project.flag_settings, contributions.setting_origins)
    members = composition.member_resource_paths
    configuration = _configuration(ctx, project, contributions, members)
    project_file = _configuration_file(ctx, configuration, "")
    files = _collect_files(project, selection)
    purposes = _purpose_project_files(ctx, configuration, files)
    initialized = _initialize(ctx, project, files)
    metadata_index = _metadata_index(ctx, files)
    relationships = depset(transitive = [dependency.relationships for dependency in selection.dependencies])
    graph = project_graph(
        ctx,
        project_file,
        members,
        files.import_resource_paths,
        composition.member_owners,
        files.import_owners,
        relationships,
        ignored = files.ignored,
        index = metadata_index,
        extensions = files.extensions,
        addons = selection.addons,
        units = files.units,
    )
    return [DefaultInfo(files = depset([project_file] + files.combined.values(), transitive = [files.imports])), GodotViewInfo(
        project = project,
        runtime_project_file = project_file,
        export_project_file = purposes.export,
        shell_project_file = purposes.shell,
        editor_project_file = purposes.editor,
        composed_settings = _composed_settings(configuration, str(project.label)),
        addons = selection.addons,
        editor_resource_paths = _editor_resource_paths(composition) | files.editor_parts.resource_paths,
        editor_imports = depset(transitive = [files.imports, files.editor_parts.imports]),
        importer_resource_paths = files.importers.resource_paths,
        importer_imports = files.importers.imports,
        export_configuration = {
            "settings": configuration.settings,
            "autoloads": configuration.autoloads,
            "main_scene": configuration.main_scene,
            "importer_plugins": files.importers.plugins,
        },
        member_resource_paths = members,
        import_resource_paths = files.import_resource_paths,
        import_owners = files.import_owners,
        ignored_resource_paths = files.ignored,
        member_owners = composition.member_owners,
        relationships = relationships,
        imports = files.imports,
        initialized = initialized,
        metadata = _metadata_list(ctx, files, initialized, metadata_index),
        metadata_index = metadata_index,
        export_extensions = files.extensions,
        runtime_extensions = filter_runtime_extensions(files.extensions),
        missing_entries = configuration.missing_entries,
        graph = graph.graph,
        graph_manifest = graph.manifest,
    )]

_VIEW_ATTRS = {
    "engine": attr.string(doc = "The operation's engine, which the view imports and validates with."),
    "project": attr.label(
        doc = "The godot_project whose configuration this operation uses.",
        mandatory = True,
        providers = [GodotProjectInfo],
    ),
    "deps": attr.label_list(
        doc = """
        What the operation works on: godot_resources, which become members and import
        under the project's configuration, and add-ons, godot_addon, godot_extension
        and godot_cc_extension targets, as on godot_resources.
        """,
    ),
}

_godot_view = rule(
    doc = """
    The project an operation runs Godot on: its project's configuration over the
    resources it names, with their imports, initialization, metadata and graph.

    Internal: operation macros declare one per operation as `<name>.view`. It runs
    in the operation's project context, so its resources import under the project's
    configuration once, whichever operation reaches them.
    """,
    implementation = _view_impl,
    cfg = context_transition,
    attrs = _VIEW_ATTRS | {
        "named_addons": attr.label(
            doc = """
            The add-ons the project names, `<project>.named_addons`: reached in the
            view's context, they import their parts under it like used add-ons.
            """,
            mandatory = True,
            providers = [NamedAddonsInfo],
        ),
        "program_entry": attr.string(
            doc = """
            Label of the source run the view serves, which starts the game itself and
            so fails for an authored content-bound setting whose file the members lack;
            empty for every other operation, which leaves the setting out. A pack checks
            such settings itself.
            """,
        ),
        "_project_config": attr.label(
            default = Label("//tools/project:config"),
            executable = True,
            cfg = "exec",
        ),
        "_actions": attr.label(
            default = Label("//tools/editor_action:project"),
            executable = True,
            cfg = "exec",
        ),
        "_metadata_sync": attr.label(
            default = Label("//tools/checkout:metadata_sync"),
            executable = True,
            cfg = "exec",
        ),
        "_metadata_index": attr.label(
            default = Label("//tools/resources:index"),
            executable = True,
            cfg = "exec",
        ),
        "_resource_graph": attr.label(
            default = Label("//tools/resource_graph"),
            executable = True,
            cfg = "exec",
        ),
    } | METADATA_ATTRS,
    toolchains = [EDITOR_TOOLCHAIN],
)

def declare_view(name, project, deps, kwargs, **attrs):
    """
    Declare the view of an operation macro as `<name>.view`.

    Args:
        name: Name of the operation.
        project: The godot_project the operation names.
        deps: The operation's deps.
        kwargs: The macro's keyword arguments; the view shares their common attributes.
        **attrs: Further attributes of the view, which replace common ones.

    Returns:
        The label string of the view, relative to the package.
    """
    _godot_view(
        name = name + ".view",
        project = project,
        named_addons = named_addons_label(native.package_relative_label(project)),
        deps = deps,
        # The caller's package may inspect the staged project, as its analysis tests do.
        **(common_kwargs(kwargs) | dict(visibility = CALLER_PACKAGE) | attrs)
    )
    return ":" + name + ".view"
