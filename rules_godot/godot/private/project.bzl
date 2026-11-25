"""
Projects as configuration contexts: their configuration files and the add-ons they name.

Sections: Configuration files, Named add-ons, godot_project.
"""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load("//godot/private:actions.bzl", "run_editor_action", "write_manifest")
load("//godot/private:configuration.bzl", "PINNED_SETTINGS", "validate_autoloads", "validate_custom_feature", "validate_settings")
load("//godot/private:context.bzl", "TRANSITION_ATTRS", "reset_transition")
load("//godot/private:execution.bzl", "EDITOR_TOOLCHAIN")
load("//godot/private:flags.bzl", "FlagInfo")
load("//godot/private:import_units.bzl", "importer_staging")
load("//godot/private:paths.bzl", "exec_paths", "mapped_path", "mapped_paths", "validate_resource_path")
load("//godot/private:providers.bzl", "GodotAddonInfo", "GodotProjectInfo")
load("//godot/private:resources.bzl", "addon_closure")
load("//godot/private/config:settings.bzl", "ENGINE_FEATURE_TAGS", "entry_features")
load("//godot/private/engine:setting_kinds.bzl", "engine_sections", "setting_kinds")

visibility("//godot")

# ==== Configuration files =====================================================

_PURPOSE_MNEMONICS = {
    "runtime": "GodotProjectConfig",
    "editor": "GodotEditorConfig",
    "export": "GodotExportConfig",
    "import": "GodotImportConfig",
}

# The purposes whose configuration carries PINNED_SETTINGS: imports, initialization, which
# reads the import configuration, and exports, whose Godot checks the formats its platform
# needs and whether the imports are current against these settings.
_PINNED_PURPOSES = ["import", "export"]

def _sets_nothing(settings, autoloads, main_scene, kinds):
    """Whether a configuration sets no value over its base and applies no setting kinds."""
    return kinds == None and not any([settings, autoloads, main_scene])

def configuration_file(
        ctx,
        base,
        suffix,
        settings,
        autoloads = {},
        main_scene = "",
        purpose = "runtime",
        editor_plugins = [],
        features = None,
        kinds = None,
        left_out = None,
        context_only = False):
    """
    Construct a purpose's project.godot from base; return base itself when nothing changes.

    Args:
        ctx: Rule analysis context with a _project_config tool and the editor toolchain.
        base: The project.godot File the construction starts from.
        suffix: Distinguishes this target's outputs.
        settings: section/property keys to Godot literal values.
        autoloads: Autoload names to res:// paths.
        main_scene: res:// path of the main scene, or empty.
        purpose: "runtime", "import", "export" or "editor"; see project_config.py.
        editor_plugins: plugin.cfg res:// paths the purpose enables.
        features: JSON File of the feature tags of the editor of import actions, or None.
        kinds: The setting kinds and sections of the editor's version, from
            configuration_kinds, which decide what the purpose carries; None leaves base's
            settings as they are.
        left_out: JSON File of the authored settings the view leaves out, from
            left_out_entries, or None.
        context_only: Whether to carry no setting that names a file of the game; see
            project_config.py.

    Returns:
        The constructed File.
    """
    if purpose == "runtime" and _sets_nothing(settings, autoloads, main_scene, kinds):
        return base
    out = ctx.actions.declare_file(ctx.label.name + suffix + ".project.godot")
    data = {
        "project_file": base.path,
        "settings": settings,
        "autoloads": autoloads,
        "main_scene": main_scene,
        "purpose": purpose,
        "editor_plugins": editor_plugins,
        "context_only": context_only,
    }
    if purpose in _PINNED_PURPOSES:
        data["pinned_settings"] = PINNED_SETTINGS
    if kinds:
        data["kinds"] = kinds.kinds
        data["sections"] = kinds.sections
    files = {name: file for name, file in [("left_out", left_out), ("features", features)] if file}
    data |= {name: file.path for name, file in files.items()}
    manifest = write_manifest(ctx, suffix + ".config", data)
    ctx.actions.run(
        executable = ctx.executable._project_config,
        arguments = ["compose", "--manifest", manifest.path, "--output", out.path],
        inputs = [base] + files.values() + [manifest],
        outputs = [out],
        mnemonic = _PURPOSE_MNEMONICS[purpose],
        progress_message = "Generating %%{label} (%s)" % purpose,
    )
    return out

def configuration_kinds(ctx):
    """
    The setting kinds and sections of the registered editor's version.

    Args:
        ctx: Rule analysis context with the editor toolchain.

    Returns:
        A struct of kinds, the setting-kind table, and sections, the sections of Godot's
        own settings, as configuration_file takes them.
    """
    version = ctx.toolchains[EDITOR_TOOLCHAIN].godot.version
    return struct(kinds = setting_kinds(version), sections = engine_sections(version))

def left_out_entries(ctx, project, members, program_entry):
    """
    List the content-bound settings of the authored file that name a file a view lacks.

    Args:
        ctx: Rule analysis context with a _project_config tool and the editor toolchain,
            whose setting kinds decide which settings are content-bound.
        project: GodotProjectInfo of the view's project: its authored project.godot and
            its custom features. An override with no tag the program entry can have
            never applies there, so it needs no file; other operations' listings do not
            depend on the custom features, so variants share them.
        members: The view's member resource paths.
        program_entry: Label string of the program entry that needs these files, whose
            action fails for such a setting instead, naming the setting and its file;
            empty for other operations.

    Returns:
        The JSON File of [setting, res:// path] pairs, which configuration_file leaves out.
    """
    base = project.authored_project_file
    out = ctx.actions.declare_file(ctx.label.name + ".left_out.json")
    manifest = write_manifest(ctx, ".left_out.config", {
        "project_file": base.path,
        "kinds": configuration_kinds(ctx).kinds,
        "members": sorted(members),
        "program_entry": program_entry,
        "features": entry_features(project.custom_features) if program_entry else None,
    })
    ctx.actions.run(
        executable = ctx.executable._project_config,
        arguments = ["left-out", "--manifest", manifest.path, "--output", out.path],
        inputs = [base, manifest],
        outputs = [out],
        mnemonic = "GodotConfigurationEntries",
        progress_message = "Generating %{label}",
    )
    return out

# ==== Named add-ons ===========================================================

NamedAddonsInfo = provider(
    doc = "The add-ons a project names, reached by views and a pack's native path without the project.",
    fields = {"addons": "postorder depset of GodotAddonInfo, with the add-ons those need, dependencies first"},
)

def _named_addons_impl(ctx):
    return [NamedAddonsInfo(addons = addon_closure([target[GodotAddonInfo] for target in ctx.attr.deps]))]

# The add-ons a project names, without the project, which cannot depend on them in its own
# context: their imports read it. A view reaches them here in its context, where they import
# their parts like used add-ons; a pack's native path reaches them with the context reset, on
# a deps edge the aspects of rules_android and rules_apple follow.
_named_addons = rule(
    implementation = _named_addons_impl,
    attrs = {
        "deps": attr.label_list(providers = [GodotAddonInfo]),
    },
)

def named_addons_label(project):
    """The label of the helper that holds the add-ons the project with this label names."""
    return project.same_package_label(project.name + ".named_addons")

# ==== godot_project ===========================================================

def _authored_autoloads(ctx):
    """
    List the autoloads of the authored project.godot, which content validations register.

    An edit of the authored file that leaves its autoloads as they are produces the same
    list, so it reruns no validation.

    Returns:
        The JSON File of autoload names to their values as written, such as *uid://...
    """
    out = ctx.actions.declare_file(ctx.label.name + ".autoloads.json")
    ctx.actions.run(
        executable = ctx.executable._project_config,
        arguments = ["autoloads", "--project-file", ctx.file.project_file.path, "--output", out.path],
        inputs = [ctx.file.project_file],
        outputs = [out],
        mnemonic = "GodotAuthoredAutoloads",
        progress_message = "Generating %{label}",
    )
    return out

def _importer_index(named):
    """
    Index the importers of named add-ons by the suffixes their importer roles declare.

    Args:
        named: GodotAddonInfo of the add-ons a project names, dependencies first.

    Returns:
        A dict of suffixes to the add-ons declaring them, in the order of named.
    """
    importers = {}
    for addon in named:
        for suffix in addon.importer_suffixes:
            importers.setdefault(suffix, []).append(addon)
    return importers

def _probed_importer(addon):
    """What the importer probe checks of an add-on: its declared suffixes against the importers its editor-part scripts and extensions register."""
    return {
        "label": str(addon.label).removeprefix("@@"),
        "suffixes": addon.importer_suffixes,
        # Godot registers no importer of a script it ignores.
        "scripts": sorted([
            "res://" + path
            for path in addon.editor_files.member_resource_paths
            if path.endswith(".gd") and path not in addon.editor_files.ignored_resource_paths
        ]),
        "plugin": "res://" + addon.plugin_config if addon.plugin_config else "",
        "native": bool(addon.extensions),
        "member_resource_paths": exec_paths(addon.importer_resource_paths) if addon.extensions else {},
    }

def _custom_features(settings):
    """
    Return the custom features the build settings give in this configuration.

    A string setting gives its value, none when empty; a boolean setting gives its own
    name when it is true.

    Args:
        settings: The custom_features targets, each with BuildSettingInfo.

    Returns:
        The tags, sorted, each once.
    """
    tags = {}
    for setting in settings:
        value = setting[BuildSettingInfo].value
        if type(value) == "bool":
            tag = setting.label.name if value else ""
        elif type(value) == "string":
            tag = value
        else:
            fail("%s is no string or boolean build setting" % setting.label)
        if tag:
            validate_custom_feature(setting.label, tag, ENGINE_FEATURE_TAGS)
            tags[tag] = True
    return sorted(tags)

def _flag_settings(ctx):
    """
    Return the settings the project's settings_from_flags give in this configuration.

    A string becomes a Godot string, an int an int and a bool a bool.

    Returns:
        A dict of setting keys to Godot literals.
    """
    values = {}
    flags = {}
    for flag, key in ctx.attr.settings_from_flags.items():
        label = str(flag.label).removeprefix("@@")
        if key in flags:
            fail("%s and %s both set the setting %s" % (flags[key], label, key))
        value = (flag[BuildSettingInfo] if BuildSettingInfo in flag else flag[FlagInfo]).value
        if type(value) not in ["string", "int", "bool"]:
            fail("%s: settings_from_flags takes string, int and bool build settings, not %s" % (label, type(value)))
        values[key] = json.encode(value)
        flags[key] = label
    validate_settings(values)
    return values

def _flag_setting_overrides(ctx):
    """
    Check that the authored project.godot has no feature override of a setting from a flag.

    Such an override would hide the flag's value where its tag applies. The check reads
    the flags' labels, not their values, so a new value reruns it as little as imports.

    Returns:
        The File the check writes, for the _validation output group; None without
        settings_from_flags.
    """
    if not ctx.attr.settings_from_flags:
        return None
    out = ctx.actions.declare_file(ctx.label.name + ".flag_overrides.checked")
    manifest = write_manifest(ctx, ".flag_overrides", {
        "project_file": ctx.file.project_file.path,
        "flag_keys": {
            key: str(flag.label).removeprefix("@@")
            for flag, key in ctx.attr.settings_from_flags.items()
        },
    })
    ctx.actions.run(
        executable = ctx.executable._project_config,
        arguments = ["shadowed", "--manifest", manifest.path, "--output", out.path],
        inputs = [ctx.file.project_file, manifest],
        outputs = [out],
        mnemonic = "GodotFlagSettingOverrides",
        progress_message = "Validating %{label}",
    )
    return out

def _import_configuration(ctx):
    """
    The project.godot that imports read: the project's settings for the import purpose.

    The import settings of its importers reach only the Godot processes that stage them.
    """
    settings = dict(ctx.attr.settings)
    settings.update(ctx.attr.setting_overrides)

    # Overrides of feature tags the editor of import actions lacks are runtime settings.
    features = ctx.actions.declare_file(ctx.label.name + ".import_features.json")
    run_editor_action(
        ctx,
        "features",
        ".features",
        features,
        {
            "project_file": mapped_path(ctx.file.project_file),
            "setting_keys": sorted(settings),
        },
        depset([ctx.file.project_file]),
        depset(),
        "GodotImportFeatures",
        "Probing %{label}",
        path_mapping = True,
    )
    return configuration_file(
        ctx,
        ctx.file.project_file,
        ".import",
        settings,
        purpose = "import",
        features = features,
        kinds = configuration_kinds(ctx),
    )

def _importable_suffixes(ctx, import_project_file, named_list):
    """
    The directory listing the file suffixes Godot's importers handle in this context.

    Godot itself reports them, and which suffixes the importers of each named add-on with
    an importer role convert.
    """
    importer_addons = [addon for addon in named_list if addon.importer_suffixes]
    staging = importer_staging(struct(setting_overrides = ctx.attr.setting_overrides), importer_addons)
    probed = staging.resource_paths
    importable = ctx.actions.declare_directory(ctx.label.name + ".importable")
    run_editor_action(
        ctx,
        "suffixes",
        ".importable",
        importable,
        {
            "project_file": mapped_path(import_project_file),
            "member_resource_paths": mapped_paths(probed),
            "editor_plugins": staging.plugins,
            "importers": [_probed_importer(addon) for addon in importer_addons],
        },
        depset([import_project_file] + probed.values()),
        depset(),
        "GodotImportableSuffixes",
        "Probing %{label}",
        path_mapping = True,
    )
    return importable

def _project_impl(ctx):
    validate_settings(ctx.attr.settings)
    validate_settings(ctx.attr.setting_overrides)
    validate_autoloads(ctx.attr.autoloads)
    validate_autoloads(ctx.attr.autoload_overrides)
    flag_settings = _flag_settings(ctx)
    named = addon_closure([target[GodotAddonInfo] for target in ctx.attr.deps])
    named_list = named.to_list()

    importers = _importer_index(named_list)
    import_project_file = _import_configuration(ctx)
    importable = _importable_suffixes(ctx, import_project_file, named_list)
    context_files = {}
    for target, path in ctx.attr.context_files.items():
        validate_resource_path(path)
        context_files[path] = target.files.to_list()[0]

    # Outside every operation a project builds nothing; operations build what they use.
    checked = _flag_setting_overrides(ctx)
    return [
        DefaultInfo(),
        OutputGroupInfo(_validation = depset([checked] if checked else [])),
        GodotProjectInfo(
            label = ctx.label,
            import_configuration = import_project_file,
            importable = importable,
            authored_project_file = ctx.file.project_file,
            authored_autoloads = _authored_autoloads(ctx),
            settings = dict(ctx.attr.settings),
            setting_overrides = dict(ctx.attr.setting_overrides),
            autoloads = dict(ctx.attr.autoloads),
            autoload_overrides = dict(ctx.attr.autoload_overrides),
            main_scene = ctx.attr.main_scene,
            context_files = context_files,
            importers = importers,
            named_addons = named,
            custom_features = _custom_features(ctx.attr.custom_features),
            flag_settings = flag_settings,
        ),
    ]

_godot_project = rule(
    doc = "The configuration context of a product; the rule behind godot_project.",
    implementation = _project_impl,
    attrs = {
        "project_file": attr.label(
            doc = "Declared project.godot file used as the base configuration.",
            mandatory = True,
            allow_single_file = True,
        ),
        "settings": attr.string_dict(
            doc = """
            section/property -> Godot literal string. Every setting the import
            purpose keeps affects every import of the project.
            """,
        ),
        "autoloads": attr.string_dict(
            doc = """
            Autoload name to res:// path, optionally prefixed with '*' for a singleton;
            conflicts require explicit overrides. An operation whose resources lack the
            script leaves the autoload out; a pack without required_packs and a source
            run fail instead.
            """,
        ),
        "setting_overrides": attr.string_dict(
            doc = "Explicitly replace conflicting setting contributions of add-ons.",
        ),
        "autoload_overrides": attr.string_dict(
            doc = "Explicitly replace conflicting autoload contributions of add-ons.",
        ),
        "main_scene": attr.string(
            doc = """
            Resource path of the main scene, with optional res:// prefix. An operation
            whose resources lack it leaves it out; a pack without required_packs and a
            source run fail instead.
            """,
        ),
        "context_files": attr.label_keyed_string_dict(
            doc = """
            Single-file target to resource path of files bound to the context itself,
            such as an application icon a setting names.
            """,
            allow_files = True,
        ),
        "custom_features": attr.label_list(
            doc = """
            The build settings whose values are the project's Godot custom features,
            such as bazel_skylib's string_flag (its value) and bool_flag (its name when
            true); its packs and source runs have them. See
            [Custom features](../../configuration.md#custom-features).
            """,
            providers = [BuildSettingInfo],
        ),
        "settings_from_flags": attr.label_keyed_string_dict(
            doc = """
            Build settings whose values become project settings, as flag ->
            section/property key, such as
            `{"@autoload_rules_godot//godot:build_number": "application/config/build_number"}`.
            A string becomes a Godot string, an int an int and a bool a bool; the value
            is written also when it is empty or 0. Packs export with the values and
            source runs start with them; imports, the editor and every other action
            never read them, so a new value reruns only exports. They replace the
            authored value; a pack's own settings replace them. A setting of the
            project or an add-on with the same key, or a feature override of it in
            project.godot or contributed settings, fails: it would conflict with the
            value or hide it. No check resolves a res:// path a value names.
            See [Settings from build settings](../../configuration.md#settings-from-build-settings).
            """,
            providers = [[BuildSettingInfo], [FlagInfo]],
        ),
        "deps": attr.label_list(
            doc = """
            The add-ons the project names: those no content of its operations uses,
            such as an editor-only add-on with editor tooling,
            extensions every operation loads, and every add-on whose importer the
            project's content needs. Every operation of the project contains them, and
            they import their parts under the project like used add-ons. Their
            importer_suffixes and import_settings apply to the project's imports.
            godot_addon, godot_extension and godot_cc_extension targets.
            """,
            providers = [GodotAddonInfo],
            cfg = reset_transition,
        ),
        "_project_config": attr.label(
            default = Label("//godot/private:project_config"),
            executable = True,
            cfg = "exec",
        ),
        "_actions": attr.label(
            default = Label("//tools:godot_actions"),
            executable = True,
            cfg = "exec",
        ),
    } | TRANSITION_ATTRS,
    toolchains = [EDITOR_TOOLCHAIN],
)

# A symbolic macro, so that every project is visible to //godot/private:project, which
# names it as the context of the resources an operation reaches, and is never testonly,
# since production resources import under it too.
def _project_macro_impl(name, visibility, testonly, deps, **kwargs):
    if testonly:
        fail("%s: a godot_project cannot be testonly; every resources target imports under it" % name)
    _godot_project(name = name, visibility = visibility, testonly = False, deps = deps, **kwargs)

    # Visible like the project: the views of operations that name it reach it.
    _named_addons(
        name = name + ".named_addons",
        deps = deps,
        visibility = visibility,
        testonly = False,
        tags = ["manual"],
    )

godot_project = macro(
    doc = """
    Declare the configuration context of a product: its project.godot, settings,
    autoloads, main scene and the add-ons it names.

    The project holds no resources. Every operation that runs Godot, such as
    godot_pack, godot_run or godot_test, names a project and the
    resources it works on; each resources target imports once under the project's
    configuration, and every operation of the project for the same target platform
    reuses that import. Settings that reach imports are the project's own, filtered by
    the import purpose: the main scene, autoloads, settings naming files, keys outside
    Godot's own sections and feature overrides the editor never applies stay out of
    imports. The autoloads and
    settings of the add-ons an operation contains merge with the project's per
    operation, the project's last; conflicts require setting_overrides or
    autoload_overrides. The add-ons the project names in deps are in every operation of
    the project and import their parts under it like used add-ons.
    A project is never testonly, also in a package with default_testonly: every resources
    target imports under it, production resources included.

    Example:
    ```starlark
    godot_project(
        name = "project",
        project_file = "project.godot",
        main_scene = "main.tscn",
    )

    godot_pack(
        name = "pack",
        project = ":project",
        deps = [":main", ":textures"],
    )
    ```

    See [resource and configuration semantics](../../resources.md).

    ### Default outputs
    - metadata (none): name the configuration context operations use; no build or run behavior

    ### Generated targets
    - `{name}.named_addons` (metadata): The add-ons the project names, which the operations of the project reach without the project; not for direct use
      - purpose: analysis_boundary
      - visibility: caller
    """,
    implementation = _project_macro_impl,
    inherit_attrs = _godot_project,
    # buildifier: disable=attr-applicable_licenses
    attrs = {
        "package_metadata": None,
        "expect_failure": None,
        "transitive_configs": None,
        "compatible_with": None,
        "restricted_to": None,
        "aspect_hints": None,
        "toolchains": None,
        "exec_group_compatible_with": None,
    },
)
