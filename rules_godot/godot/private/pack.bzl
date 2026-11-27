"""PCK exports of a project's view, with the native code of each platform slice."""

load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/engine/private:selection.bzl", "ENGINE_ATTRS", "ENGINE_DOC", "engine_transition")
load("//godot/private:actions.bzl", "run_editor_action", "write_manifest")
load("//godot/private:configuration.bzl", "validate_export_options", "validate_preset_settings", "validate_settings")
load("//godot/private:execution.bzl", "EDITOR_TOOLCHAIN")
load("//godot/private:export_options.bzl", "resolve_export_options")
load("//godot/private:import_units.bzl", "GAME_ONLY")
load("//godot/private:metadata.bzl", "METADATA", "METADATA_ATTRS", "metadata_entry", "metadata_kinds")
load("//godot/private:pack_conversion.bzl", "PACK_CONVERSION_ATTRS", "pack_conversion")
load("//godot/private:pack_project.bzl", "GodotPackNativeInfo", "godot_pack_native", "pack_project")
load("//godot/private:paths.bzl", "declared_path", "exec_paths", "with_extensions_for")
load("//godot/private:project.bzl", "configuration_file", "configuration_kinds", "left_out_entries", "named_addons_label")
load("//godot/private:providers.bzl", "GodotProjectInfo")
load("//godot/private:release.bzl", "RELEASE_ATTRS", "app_version")
load("//godot/private:shell_assets.bzl", "pack_shell_assets")
load("//godot/private:variant.bzl", "VARIANT_ATTRS", "variant")
load("//godot/private:view.bzl", "GodotViewInfo", "declare_view", "filter_runtime_extensions", "require_entries")
load("//godot/private/config:settings.bzl", "configured_context", "context_attrs")
load("//godot/private/config:transitions.bzl", "content_transition", "platform_slice_transition", "project_transition")
load("//godot/private/engine:profiles.bzl", "engine_profile")

visibility("//godot")

# The project setting scripts read the application version from.
_VERSION_SETTING = "application/config/version"

def _literal_filter_path(path):
    # Godot reads the exclusion filter as comma-separated glob patterns.
    if any([character in path for character in ["*", ",", "?", "[", "]"]]):
        fail((
            "Excluded resource res://%s cannot be a literal export filter entry; " +
            "it contains one of * , ? [ ]"
        ) % path)

def _select(ctx, project, request):
    """
    Select over the project's graph; return the report and the pack's content File.

    Args:
        ctx: Pack rule analysis context.
        project: The pack's view combined with its platform slices, from pack_project.
        request: struct of the entry_points, the extension_paths and
            extension_library_paths, the excluded paths and the content the required
            packs make available.
    """
    selection = ctx.actions.declare_file(ctx.attr.output_name + ".selection.json")
    content = ctx.actions.declare_file(ctx.attr.output_name + ".content.json")
    manifest = write_manifest(ctx, ".selection-manifest", {
        "pack": ctx.attr.pack_label,
        "selection": ctx.attr.packing,
        "entry_points": request.entry_points,
        "extensions": sorted(request.extension_paths),
        "excluded": sorted(request.excluded),
        "extension_library_paths": sorted(request.extension_library_paths),
        "required": [file.path for file in request.available.to_list()],
    })
    ctx.actions.run(
        executable = ctx.executable._pack_selection,
        arguments = [
            "--manifest",
            manifest.path,
            "--graph",
            project.graph.path,
            "--project-manifest",
            project.graph_manifest.path,
            "--output",
            selection.path,
            "--content",
            content.path,
        ],
        inputs = depset(
            [manifest, project.graph, project.graph_manifest],
            transitive = [request.available],
        ),
        outputs = [selection, content],
        mnemonic = "GodotPackSelection",
        progress_message = "Generating %{label}",
    )
    return selection, content

def _engine_assets(ctx, profile):
    """Godot's default application icon and boot splash of an engine profile."""
    files = {file.basename: file for file in ctx.files._engine_assets}
    return struct(
        icon = files[profile["assets"]["icon"]],
        splash = files[profile["assets"]["splash"]],
    )

def _check_metadata(ctx, project, excluded, kind):
    """
    Fail while the pack's text files lack the metadata kind its flag requires.

    The check filters the project's metadata index to the pack's files, so
    script edits leave it current.

    Args:
        ctx: Pack rule analysis context.
        project: The pack's view combined with its platform slices, from pack_project.
        excluded: Paths the pack never contains.
        kind: A key of METADATA.

    Returns:
        The validation output File.
    """
    spec = METADATA[kind]
    manifest = write_manifest(ctx, "." + kind, {
        "kind": kind,
        # Labels as users write them, without the main repository's @@.
        "pack": ctx.attr.pack_label.removeprefix("@@"),
        "project": str(project.view.project.label).removeprefix("@@"),
        "index": project.view.metadata_index.path,
        "checked": sorted([
            path
            for path in project.member_resource_paths
            if path.endswith(spec.texts) and path not in excluded and path not in project.view.ignored_resource_paths
        ]),
    })
    checked = ctx.actions.declare_file(ctx.label.name + "." + kind + ".checked")
    ctx.actions.run(
        executable = ctx.executable._metadata_index,
        arguments = ["check", "--manifest", manifest.path, "--output", checked.path],
        inputs = [manifest, project.view.metadata_index],
        outputs = [checked],
        mnemonic = spec.mnemonic,
        progress_message = spec.progress_message,
    )
    return checked

def _write_pack(ctx, project, export, outputs):
    """
    Write the pack's PCK without Godot's conversions, from a configuration export.

    The configuration export runs Godot on the pack's project without its files, so a
    content change reruns only the writer, which needs no editor.

    Args:
        ctx: Pack rule analysis context.
        project: The pack's view combined with its platform slices, from pack_project.
        export: struct of the exported project_file, the manifest fields of the pack's
            export preset and content, the content and metadata index files those
            fields name, and the extension_library_paths, which the PCK never holds.
        outputs: struct of the pck and report Files.
    """
    preset = export.preset
    view = project.view

    # The configuration export loads the extension editor libraries and the importers, as
    # the pack's export does; the settings they register shape project.binary.
    tools = with_extensions_for({}, project.export_extensions, "editor") | view.importer_resource_paths
    configuration = ctx.actions.declare_file(ctx.attr.output_name + ".configuration.pck")
    facts = ctx.actions.declare_file(ctx.attr.output_name + ".configuration.json")
    run_editor_action(
        ctx,
        "configuration",
        ".configuration",
        configuration,
        # It stages neither the content nor its import inputs.
        preset | {
            "member_resource_paths": exec_paths(tools),
            "import_resource_paths": {},
            "runtime_descriptors": {},
        },
        depset([export.project_file] + tools.values()),
        view.importer_imports,
        "GodotPackConfiguration",
        "Exporting %{label}",
        report = facts,
    )
    members = {
        path: file
        for path, file in project.member_resource_paths.items()
        if path not in export.extension_library_paths
    }
    manifest = write_manifest(ctx, ".write", preset | export.contents | {
        "member_resource_paths": exec_paths(members),
        "configuration": configuration.path,
        "configuration_facts": facts.path,
        "version": ctx.toolchains[EDITOR_TOOLCHAIN].godot.version,
    })
    arguments = ctx.actions.args()
    arguments.add_all(["--manifest", manifest, "--output", outputs.pck, "--report", outputs.report])
    arguments.add_all(view.imports, before_each = "--import", expand_directories = False)
    ctx.actions.run(
        executable = ctx.executable._pack_writer,
        arguments = [arguments],
        inputs = depset(
            [manifest, configuration, facts] + export.files + members.values() + view.import_resource_paths.values(),
            transitive = [view.imports],
        ),
        outputs = [outputs.pck, outputs.report],
        mnemonic = "GodotPackWrite",
        progress_message = "Exporting %{label}",
    )

_ExportInfo = provider(
    doc = "Export metadata of the content configuration, without each platform slice's project.",
    fields = {
        "fields": "dict of the GodotPackInfo fields the export sets",
        "context_files": "GodotProjectInfo.context_files of the pack's project",
    },
)

def _start_checks(ctx, view):
    """
    The checks of a pack that may start the game: one without required packs.

    It needs every file its configuration names: the declared entries now, the authored
    project.godot's in a check of the settings its view leaves out, whose values only a
    build reads.
    """
    if ctx.attr.required_packs:
        return []
    require_entries(view)
    return [left_out_entries(
        ctx,
        view.project,
        view.member_resource_paths,
        ctx.attr.pack_label.removeprefix("@@"),
    )]

def _synthesized_cpus(context, profile):
    """The CPUs of an iOS Simulator platform slice the engine profile lacks, which the export synthesizes."""
    if context.operating_system != "ios" or context.environment != "simulator":
        return []
    return [cpu for cpu in context.cpus if cpu not in profile["ios"]["cpus"]]

def _export_platform(ctx):
    """
    The pack's platform slice, editor version, engine profile and resolved export options.

    Returns:
        A struct of the configured context, version, profile, resolved export options,
        the CPUs the export synthesizes and the features the platform slice derives.
    """
    context = configured_context(ctx)
    version = ctx.toolchains[EDITOR_TOOLCHAIN].godot.version
    profile = engine_profile(version)
    resolved = resolve_export_options(ctx.attr.export_options, context, profile, version)
    validate_export_options(ctx.attr.export_options)
    synthesized = _synthesized_cpus(context, profile)
    return struct(
        context = context,
        version = version,
        profile = profile,
        resolved = resolved,
        synthesized = synthesized,
        derived_features = (["simulator"] if context.environment == "simulator" else []) + synthesized,
    )

def _editor_files(project):
    """
    The extensions' editor files, which every platform slice must stage alike.

    The export's editor loads every extension's tool configuration, so the export waits
    for no extension runtime library.
    """
    editor_resource_paths = {}
    for extension in project.export_extensions:
        for path, file in extension.editor_resource_paths.items():
            if editor_resource_paths.setdefault(path, file) != file:
                fail("Platform slices stage different editor files at res://%s" % path)
    return editor_resource_paths

def _runtime_layout(project):
    """
    The extensions' runtime files and descriptors.

    The pack action writes the runtime descriptors, which Godot does not pack: its editor
    staged the tool configuration's.

    Returns:
        A struct of extension_paths and extension_library_paths, the runtime files and
        libraries, and runtime_descriptors, the descriptors by resource path.
    """
    extension_paths = {}
    extension_library_paths = {}
    runtime_descriptors = {}
    for extension in project.runtime_extensions:
        descriptor_path = extension.descriptor_path
        for path in extension.runtime_resource_paths:
            extension_paths[path] = True
            if path != descriptor_path:
                extension_library_paths[path] = True
        runtime_descriptors[descriptor_path] = project.member_resource_paths[descriptor_path]
    return struct(
        extension_paths = extension_paths,
        extension_library_paths = extension_library_paths,
        runtime_descriptors = runtime_descriptors,
    )

def _check_filters(view, layout, editor_resource_paths):
    """Check every path the export excludes; these are known early."""
    for path in (
        view.import_resource_paths.keys() +
        layout.extension_library_paths.keys() +
        editor_resource_paths.keys() +
        view.importer_resource_paths.keys()
    ):
        _literal_filter_path(path)

def _pack_settings(ctx):
    """The pack's settings, with the application version unless they set it."""
    validate_settings(ctx.attr.settings, main_scene_overrides = False)
    settings = dict(ctx.attr.settings)
    release = app_version(ctx)
    if release and _VERSION_SETTING not in settings:
        settings[_VERSION_SETTING] = json.encode(release)
    return settings

def _pack_project_files(ctx, view, settings):
    """
    The project.godot files the export and the shell probe read.

    Pack settings and the project's settings from flags replace keys of the exported
    configuration only; the project's imports and initialization never see them. The
    shell probe gets no settings from flags: they change with every build, such as a
    build number, and name no file of the shell assets.

    Returns:
        A struct of export, the exported project.godot, and shell, the probe's.
    """
    exported = view.project.flag_settings | settings
    export = view.export_project_file
    shell = view.shell_project_file
    if exported:
        export = configuration_file(
            ctx,
            export,
            ".pack",
            exported,
            purpose = "export",
            editor_plugins = view.export_configuration["importer_plugins"],
        )
    if settings:
        shell = configuration_file(
            ctx,
            shell,
            ".shell",
            settings,
            purpose = "export",
            kinds = configuration_kinds(ctx),
            context_only = True,
        )
    return struct(export = export, shell = shell)

def _pack_content(ctx, project, layout, excluded):
    """
    Select the pack's content over its project's graph.

    The selection checks what the pack's files reference, such as files Godot's export
    leaves out. Which members a reachable pack or one with required packs contains is
    known only after scanning them. Any other pack contains every member, and its
    selection is a check beside the export, which does not wait for the scan.

    Returns:
        A struct of the selection report, the content File, the content the required
        packs make available, and whether the selection is a check of its own.
    """
    required = [target[GodotPackInfo] for target in ctx.attr.required_packs]
    available = depset(transitive = [pack.available for pack in required])
    selection, content = _select(ctx, project, struct(
        entry_points = [
            declared_path(project.member_resource_paths, path, "Entry point")
            for path in ctx.attr.entry_points
        ],
        extension_paths = layout.extension_paths,
        excluded = excluded,
        extension_library_paths = layout.extension_library_paths,
        available = available,
    ))
    every_member = ctx.attr.packing != "reachable" and not required
    if every_member:
        content = write_manifest(ctx, ".content", {
            "pack": ctx.attr.pack_label,
            "resources": exec_paths({
                path: file
                for path, file in project.member_resource_paths.items()
                if path not in excluded and path not in layout.extension_library_paths
            }),
        })
    return struct(selection = selection, content = content, available = available, checked = every_member)

def _preset(ctx, view, plan):
    """The export preset of the pack and of Godot's report about it, as manifest fields."""
    resolved = plan.platform.resolved
    return {
        "project_file": plan.project_files.export.path,
        "member_resource_paths": exec_paths(plan.pack_members),
        "runtime_descriptors": exec_paths(plan.layout.runtime_descriptors),
        "import_resource_paths": exec_paths(view.import_resource_paths),
        "export_options": resolved.preset_options,
        "preset_prelude": resolved.preset_prelude,
        "preset_platform": plan.platform.context.preset_platform,
        # The project's custom features, then those the platform slice derives.
        "features": view.project.custom_features + plan.platform.derived_features,
        "owner": ctx.attr.pack_label.removeprefix("@@"),
        "synthesized_cpu_features": plan.platform.synthesized,
        "preset_settings": ctx.attr.preset_settings,
        "authored_export_options": ctx.attr.export_options,
        "variant": plan.variant,
    }

def _content_fields(ctx, view, plan):
    """The manifest fields of the pack's content, and the metadata index Files they name."""
    contents = {
        "content": plan.content.content.path,
        "extension_library_paths": sorted(plan.layout.extension_library_paths),
        # Godot exports no file it ignores; the check expects none of them.
        "ignored_paths": sorted(view.ignored_resource_paths),
    }
    if not view.metadata_index:
        return contents, []
    return contents | metadata_entry(
        view.metadata_index.path,
        metadata_kinds(ctx, ["assign", "sync", "require"]),
    ), [view.metadata_index]

def _export(ctx, project, plan, outputs):
    """Export the pack's PCK and report, through Godot or the pack writer."""
    contents, metadata_files = _content_fields(ctx, project.view, plan)
    if pack_conversion(ctx) != "godot":
        _write_pack(ctx, project, struct(
            project_file = plan.project_files.export,
            preset = plan.preset,
            contents = contents,
            files = [plan.content.content] + metadata_files,
            extension_library_paths = plan.layout.extension_library_paths,
        ), outputs)
        return
    run_editor_action(
        ctx,
        "pack",
        ".pack",
        outputs.pck,
        plan.preset | contents,
        depset([plan.content.content, plan.project_files.export] + metadata_files, transitive = [plan.export_inputs]),
        plan.export_imports,
        "GodotPack",
        "Exporting %{label}",
        report = outputs.report,
    )

def _probe_shell(ctx, view, plan, shell):
    """
    Probe Godot's shell assets and export options for the pack's platform.

    The probe names no autoload and enables no plugin, so it runs no script or scene, and
    game-only files do not invalidate the facts. Godot reports hidden options only by
    name; reflection finds the others.
    """
    option_names = sorted(
        plan.platform.resolved.rejected_options.keys() +
        plan.platform.profile["hidden_export_options"].get(plan.platform.context.operating_system, []),
    )
    shell_resource_paths = {path: file for path, file in plan.shell_members.items() if not path.endswith(GAME_ONLY)}
    run_editor_action(
        ctx,
        "shell",
        ".shell",
        shell.facts,
        plan.preset | {
            "project_file": plan.project_files.shell.path,
            "member_resource_paths": exec_paths(shell_resource_paths),
            "shell": shell.spec | {"option_names": option_names},
        },
        depset(
            [plan.project_files.shell, plan.assets.icon, plan.assets.splash] + shell_resource_paths.values() + view.import_resource_paths.values(),
            transitive = [view.imports],
        ),
        view.imports,
        "GodotShellAssets",
        "Probing %{label}",
        outputs = shell.outputs,
    )

def _check_options(ctx, facts):
    """Check the authored export options against the exporter's live registration."""
    checked = ctx.actions.declare_file(ctx.label.name + ".options.checked")
    authored = write_manifest(ctx, ".options", {"authored_export_options": ctx.attr.export_options})
    ctx.actions.run(
        executable = ctx.executable._actions,
        arguments = [
            "check-options",
            "--manifest",
            authored.path,
            "--facts",
            facts.path,
            "--output",
            checked.path,
        ],
        inputs = [authored, facts],
        outputs = [checked],
        mnemonic = "GodotExportOptions",
        progress_message = "Validating %{label}",
    )
    return checked

def _staged_members(project, view):
    """
    The members the export and the shell probe stage, with the extensions' editor files.

    The export also stages the importers of the files it exports, without which its scan
    would skip those files; they are staged, never content.
    """
    shell_members = with_extensions_for(project.member_resource_paths, project.export_extensions, "editor")
    return shell_members | view.importer_resource_paths, shell_members

def _pack_plan(ctx, project):
    """Decide everything the pack's actions read, with the pack's checks in their order."""
    view = project.view
    checks = _start_checks(ctx, view)
    platform = _export_platform(ctx)
    editor_resource_paths = _editor_files(project)
    pack_members, shell_members = _staged_members(project, view)
    layout = _runtime_layout(project)
    _check_filters(view, layout, editor_resource_paths)
    if ctx.attr.entry_points and ctx.attr.packing != "reachable":
        fail("entry_points require packing = \"reachable\"")
    project_files = _pack_project_files(ctx, view, _pack_settings(ctx))
    excluded = {}
    content = _pack_content(ctx, project, layout, excluded)

    # A pack exported in the editor variant is a debug pack, as the editor has the debug
    # feature tags; a godot_app of that variant runs its view and exports none.
    selected = "debug" if variant(ctx) == "editor" else variant(ctx)
    export_imports = depset(transitive = [view.imports, view.importer_imports])
    fields = dict(
        checks = checks + ([content.selection] if content.checked else []),
        platform = platform,
        layout = layout,
        pack_members = pack_members,
        shell_members = shell_members,
        project_files = project_files,
        excluded = excluded,
        content = content,
        variant = selected,
        export_imports = export_imports,
        export_inputs = depset(
            pack_members.values() + layout.runtime_descriptors.values() +
            view.import_resource_paths.values(),
            transitive = [export_imports],
        ),
        assets = _engine_assets(ctx, platform.profile),
    )
    fields["preset"] = _preset(ctx, view, struct(**fields))
    return struct(**fields)

def _pack_impl(ctx):
    validate_preset_settings(ctx.attr.preset_settings)
    project = pack_project(ctx)
    view = project.view
    plan = _pack_plan(ctx, project)
    outputs = struct(
        pck = ctx.actions.declare_file(ctx.attr.output_name + ".pck"),
        report = ctx.actions.declare_file(ctx.attr.output_name + ".export.json"),
    )
    shell = pack_shell_assets(
        ctx,
        plan.platform.context.preset_platform,
        plan.platform.profile,
        plan.platform.resolved.pack_options,
        plan.assets,
    )
    _export(ctx, project, plan, outputs)
    _probe_shell(ctx, view, plan, shell)
    checks = plan.checks + [_check_metadata(ctx, project, plan.excluded, kind) for kind in metadata_kinds(ctx, ["require"])]
    if ctx.attr.export_options:
        checks.append(_check_options(ctx, shell.facts))
    return [
        DefaultInfo(files = depset([outputs.pck])),
        _ExportInfo(
            context_files = view.project.context_files,
            fields = dict(
                pack_file = outputs.pck,
                pack_files = depset([outputs.pck]),
                available = depset([plan.content.content], transitive = [plan.content.available]),
                export_options = plan.platform.resolved.pack_options,
                facts = shell.facts,
                icons = shell.icons,
                splash = shell.splash,
                version = plan.platform.version,
                variant = plan.variant,
                editor_component = ctx.toolchains[EDITOR_TOOLCHAIN].godot.provenance,
            ),
        ),
        OutputGroupInfo(
            selection = depset([plan.content.selection]),
            report = depset([outputs.report]),
            # What Godot reports about the export, for comparing exporter inventories.
            export_facts = depset([shell.facts]),
            _validation = depset(checks),
        ),
    ]

_pack_export = rule(
    doc = "The export of godot_pack; see the godot_pack macro for its public contract.",
    implementation = _pack_impl,
    attrs = {
        "view": attr.label(
            doc = "The pack's view: its project over its deps, in the project context.",
            mandatory = True,
            providers = [GodotViewInfo],
        ),
        "native": attr.label(
            doc = "The pack's native path, once per platform slice.",
            mandatory = True,
            providers = [GodotPackNativeInfo],
            cfg = platform_slice_transition,
        ),
        "output_name": attr.string(mandatory = True),
        "pack_label": attr.string(mandatory = True),
        "_common_content": attr.label(default = Label("//tools/pack:common_content"), executable = True, cfg = "exec"),
        "preset_settings": attr.string_dict(
            doc = "Supported preset fields as Godot literals: script_export_mode is 0, 1 or 2. Omitted fields retain Godot defaults. Custom features come from godot_project.custom_features. See [Godot configuration](../../configuration.md).",
        ),
        "settings": attr.string_dict(
            doc = """
            Project settings for this export only, as section/property -> Godot literal
            string, for example `{"application/config/version": '"2.3.4"'}`. They
            replace the project's values in the exported configuration; imports,
            initialization and other packs keep the project's, so a change reruns
            only this export. Feature overrides such as `key.mobile` apply when the
            configured operating system or the project's custom features have the tag. Without an
            application/config/version entry here, a nonempty
            `--@autoload_rules_godot//godot:app_version` sets that setting.
            """,
        ),
        "export_options": attr.string_dict(
            doc = """
            Export preset options for this pack, as option name -> Godot literal
            string, for example `{"texture_format/etc2_astc": "true"}`. These are the
            options exporters and extensions' export plugins define in the preset's options
            section. binary_format/embed_pck and binary_format/architecture are set
            by the configured export platform and output layout.
            """,
        ),
        "_actions": attr.label(
            default = Label("//tools:godot_export"),
            executable = True,
            cfg = "exec",
        ),
        "_pack_writer": attr.label(
            default = Label("//tools/pack:writer"),
            executable = True,
            cfg = "exec",
        ),
        "_project_config": attr.label(
            default = Label("//tools/project:config"),
            executable = True,
            cfg = "exec",
        ),
        "_metadata_index": attr.label(
            default = Label("//tools/resources:index"),
            executable = True,
            cfg = "exec",
        ),
        "_engine_assets": attr.label(
            default = Label("//godot/private/engine:assets"),
        ),
        "packing": attr.string(
            doc = """
            deps: every member of deps. reachable: what the project configuration,
            entry_points, extensions and runtime_deps of used targets reach through
            detected and declared references; fails where a reached file may load
            undeclared files.
            """,
            default = "deps",
            values = ["deps", "reachable"],
        ),
        "entry_points": attr.string_list(
            doc = """
            Declared paths that reachable selection starts from in addition to the main
            scene, autoloads and other configured resources.
            """,
        ),
        "required_packs": attr.label_list(
            doc = """
            Packs whose resources this pack's references may use instead of packing
            them again; a path both declare must have the same source file. This is
            membership only, not runtime mounting or load order.
            """,
            providers = [GodotPackInfo],
        ),
        "_pack_selection": attr.label(
            default = Label("//tools/resource_graph:selection"),
            executable = True,
            cfg = "exec",
        ),
        "_resource_graph": attr.label(
            default = Label("//tools/resource_graph"),
            executable = True,
            cfg = "exec",
        ),
    } | METADATA_ATTRS | PACK_CONVERSION_ATTRS | RELEASE_ATTRS | VARIANT_ATTRS | context_attrs(),
    toolchains = [EDITOR_TOOLCHAIN],
)

def _configured_pack_impl(ctx):
    exported = ctx.attr.export[0]
    export = exported[_ExportInfo]
    native = ctx.attr.deps[0][GodotPackNativeInfo]
    context = configured_context(ctx)
    return [
        DefaultInfo(files = exported[DefaultInfo].files),
        GodotPackInfo(
            project = struct(
                member_resource_paths = native.member_resource_paths | export.context_files,
                runtime_extensions = filter_runtime_extensions(native.export_extensions),
                export_extensions = native.export_extensions,
                platform_libraries = native.platform_libraries,
                infoplists = native.infoplists,
            ),
            operating_system = context.operating_system,
            cpus = context.cpus,
            environment = context.environment,
            **export.fields
        ),
        exported[OutputGroupInfo],
    ] + ([ctx.attr.view[GodotViewInfo]] if ctx.attr.view else [])

_configured_pack = rule(
    implementation = _configured_pack_impl,
    attrs = {
        "deps": attr.label_list(mandatory = True, cfg = project_transition, providers = [GodotPackNativeInfo]),
        "export": attr.label(mandatory = True, cfg = content_transition),
        "view": attr.label(
            doc = "The pack's view in the editor variant, where a godot_app runs it from sources instead of exporting it.",
            providers = [GodotViewInfo],
        ),
    } | context_attrs() | ENGINE_ATTRS,
    cfg = engine_transition,
)

def _pack_macro_impl(name, visibility, project, deps, engine, **kwargs):
    export_kwargs = dict(kwargs)
    tags = export_kwargs.pop("tags", None) or []
    if not export_kwargs.get("deprecation"):
        export_kwargs.pop("deprecation", None)
    common = {key: value for key, value in export_kwargs.items() if key in ["deprecation", "testonly", "target_compatible_with"]}
    hidden = dict(common, tags = tags + ["manual"], visibility = ["//visibility:private"])
    pack_label = str(native.package_relative_label(":" + name))
    view = declare_view(
        name,
        project,
        deps,
        kwargs,
        tags = tags + ["manual"],
        engine = engine,
    )

    # The deps edge of the configured pack to this target is what the aspects of
    # rules_android and rules_apple follow to the platform libraries.
    godot_pack_native(
        name = name + ".native",
        deps = (deps or []) + [named_addons_label(project)],
        **hidden
    )
    _pack_export(
        name = name + ".export",
        view = view,
        native = ":" + name + ".native",
        output_name = name,
        pack_label = pack_label,
        tags = tags + ["manual"],
        **export_kwargs
    )

    # Bazel reports no deprecation within a package; consumers depend on the public target.
    _configured_pack(
        name = name,
        deps = [":" + name + ".native"],
        export = ":" + name + ".export",
        # A godot_app of the editor variant runs the view from sources; elsewhere the
        # pack's configuration would add a second configured view beside the export's.
        view = select({
            Label("//godot:editor"): view,
            "//conditions:default": None,
        }),
        visibility = visibility,
        tags = tags,
        engine = engine,
        **common
    )

godot_pack = macro(
    doc = """
    Export a project as one PCK for the selected export platform.

    The PCK contains extension descriptors, never extension libraries;
    see [export membership](../../resources.md#export-membership).
    Its extensions and platform libraries stay visible to the aspects of rules_android
    and rules_apple in each platform slice. The export itself runs once, in the content
    configuration, for all platform slices. Outside optimized builds the PCK is written
    without Godot's conversions; see [pack forms](../../resources.md#pack-forms). DefaultInfo contains the PCK; GodotPackInfo
    carries the project of each platform slice and the facts of the common export.
    OutputGroupInfo.report exposes the export report. required_packs only affects which
    files this pack contains; applications do not package the required packs, and
    nothing mounts them at runtime.

    Example: godot_pack(name = "pack", project = ":project", deps = [":game"]).
    See [export behavior](../../resources.md).
    """,
    implementation = _pack_macro_impl,
    inherit_attrs = _pack_export,
    # Inherited testonly defaults to None, so helpers get the package default_testonly.
    # This dictionary excludes inherited package_metadata; it defines no custom field.
    # Remove the exclusion when macro inheritance stops exposing that built-in attribute.
    # buildifier: disable=attr-applicable_licenses
    attrs = {
        "engine": attr.string(doc = ENGINE_DOC, configurable = False),
        "project": attr.label(
            doc = "The godot_project whose configuration this pack exports.",
            mandatory = True,
            providers = [GodotProjectInfo],
            configurable = False,
        ),
        "deps": attr.label_list(
            doc = """
            What the pack exports: godot_resources and add-ons, as on godot_resources.
            Applications reach the extensions and platform libraries of the pack's
            add-ons, the project's named ones included, through the pack.
            """,
        ),
        "view": None,
        "native": None,
        "output_name": None,
        "pack_label": None,
        "expect_failure": None,
        "transitive_configs": None,
        "compatible_with": None,
        "restricted_to": None,
        "package_metadata": None,
        "aspect_hints": None,
        "toolchains": None,
        "exec_group_compatible_with": None,
        "tags": attr.string_list(doc = "Conventional Bazel tags on this pack; internal helpers are additionally manual.", configurable = False),
        "deprecation": attr.string(doc = "Optional Bazel deprecation message for this authored pack.", configurable = False),
        "features": attr.string_list(doc = "Bazel feature requests on export actions, distinct from Godot feature tags."),
        "exec_properties": attr.string_dict(doc = "Execution properties for this pack's actions."),
        "exec_compatible_with": attr.label_list(doc = "Execution platform constraints for this pack's export tools.", configurable = False),
        "target_compatible_with": attr.label_list(doc = "Bazel target compatibility constraints for this pack and its configured export."),
    },
)
