"""
Which imports, initializations and exports stage an importer of an add-on the project names,
and the importer declarations analysis rejects (US5).

The fixture's project names `md_importer`, whose importer converts `.md` files. Analysis
does not show an import itself (action_inputs.bzl): what it stages and enables is what its
manifest `<unit>.import.json` lists, `editor_plugins` and `tools`, and the manifest of the
importer's files it reads.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:defs.bzl", "godot_addon")
load("//godot/private:providers.bzl", "GodotProjectInfo")
load("//godot/private:view.bzl", "GodotViewInfo")
load("//godot/private/tests:pack_forms.bzl", "GODOT_EXPORT")
load(":action_inputs.bzl", "expect_not_read", "expect_reads", "godot_actions", "import_manifests", "written_manifests")
load(":expected_failures.bzl", "failure_test")
load(":views.bzl", "run_view")

_FIXTURE = "//godot/private/tests/fixtures/project_with_importer"
_PLUGIN = "res://addons/md_importer/plugin.cfg"
_IMPORTER = "md_importer/importer.gd"

def _label(name):
    return str(Label(_FIXTURE + ":" + name))

# FR-016, D14: the project indexes the importers of the add-ons it names by suffix.
def _test_project_indexes_importers_by_suffix(name):
    analysis_test(
        name = name,
        target = _FIXTURE,
        impl = _project_indexes_importers_by_suffix,
    )

def _project_indexes_importers_by_suffix(env, target):
    importers = target[GodotProjectInfo].importers
    env.expect.that_collection(importers.keys()).contains_exactly(["md"])
    env.expect.that_collection([str(addon.label) for addon in importers["md"]]).contains_exactly([_label("md_importer")])

# US5 AS1, AS2 and FR-017 on both sides: the import of the unit with an own .md file stages
# and enables the importer with its files, so an importer change reruns it; the texture unit
# and the unit with an .md file only among its import inputs stage no part of the add-on,
# so an importer change reruns neither, nor the import configuration.
def _test_only_imports_of_own_md_files_stage_the_importer(name):
    analysis_test(
        name = name,
        target = _FIXTURE + ":pack",
        impl = _only_imports_of_own_md_files_stage_the_importer,
        extra_target_under_test_aspects = [godot_actions],
    )

def _only_imports_of_own_md_files_stage_the_importer(env, target):
    notes = import_manifests(target, "notes").values()
    env.expect.where(unit = "notes").that_collection(notes).has_size(1)
    for manifest in notes:
        env.expect.where(unit = "notes", field = "editor_plugins").that_collection(manifest["editor_plugins"]).contains_exactly([_PLUGIN])
        env.expect.where(unit = "notes", field = "tools").that_collection(manifest["tools"]).contains_exactly([
            "addons/md_importer/icon.svg",
            "addons/md_importer/importer.gd",
            "addons/md_importer/plugin.cfg",
            "addons/md_importer/plugin.gd",
        ])
    for unit in ["textures", "with_md_input"]:
        manifests = import_manifests(target, unit).values()
        env.expect.where(unit = unit).that_collection(manifests).has_size(1)
        for manifest in manifests:
            env.expect.where(unit = unit).that_collection(manifest.keys()).contains_none_of(["editor_plugins", "tools"])
    staged = written_manifests(target, "/md_importer.importer.resource_paths.json").values()
    env.expect.where(field = "importer resource paths").that_collection(staged).has_size(1)
    for manifest in staged:
        env.expect.where(field = "importer resource paths").that_bool(
            [path for path in manifest.values() if path.endswith(_IMPORTER)] != [],
        ).equals(True)
    expect_not_read(env, target, ["GodotImportConfig", "GodotImportFeatures"], _IMPORTER)

    # The probe checks the importer's declaration (FR-018), so it reads the importer.
    expect_reads(env, target, "GodotImportableSuffixes", _IMPORTER)

# R14, FR-016: an operation's initialization and its pack export scan its files, so they
# stage and enable the importers that convert them; the shell-assets probe does not, and an
# operation without such files stages none.
def _test_initialization_and_export_stage_the_importers_of_their_files(name):
    analysis_test(
        name = name,
        targets = {
            "pack": _FIXTURE + ":pack",
            "texture_pack": _FIXTURE + ":texture_pack",
        },
        impl = _initialization_and_export_stage_the_importers_of_their_files,
        config_settings = GODOT_EXPORT,
        extra_target_under_test_aspects = [godot_actions],
    )

def _initialization_and_export_stage_the_importers_of_their_files(env, targets):
    for mnemonic in ["GodotInitialize", "GodotPack"]:
        expect_reads(env, targets.pack, mnemonic, _IMPORTER)
    expect_not_read(env, targets.pack, ["GodotShellAssets"], _IMPORTER)
    for manifest in written_manifests(targets.pack, "/pack.view.initialize.json").values():
        env.expect.where(field = "initialization editor_plugins").that_collection(manifest["editor_plugins"]).contains_exactly([_PLUGIN])
    expect_not_read(env, targets.texture_pack, ["GodotInitialize", "GodotPack"], _IMPORTER)

# D13, D26: the settings the importer reads reach the imports and initializations that stage
# it, not the project's import configuration, so a change to them reruns only those; its
# other settings reach neither.
def _test_import_settings_reach_the_processes_staging_the_importer(name):
    analysis_test(
        name = name,
        target = _FIXTURE + ":pack",
        impl = _import_settings_reach_the_processes_staging_the_importer,
        extra_target_under_test_aspects = [godot_actions],
    )

def _import_settings_reach_the_processes_staging_the_importer(env, target):
    for manifest in import_manifests(target, "notes").values():
        env.expect.where(unit = "notes").that_dict(manifest["settings"]).contains_exactly({"md_importer/heading": '"#"'})
    for manifest in import_manifests(target, "textures").values():
        env.expect.where(unit = "textures").that_collection(manifest.keys()).not_contains("settings")
    for manifest in written_manifests(target, "/pack.view.initialize.json").values():
        env.expect.where(field = "initialization settings").that_dict(manifest["settings"]).contains_exactly({"md_importer/heading": '"#"'})
    for configuration in written_manifests(target, "/project.import.config.json").values():
        env.expect.where(field = "import configuration").that_collection(configuration["settings"].keys()).not_contains("md_importer/heading")

# FR-016: resources may use an add-on with an importer role under a project that names it.
def _test_used_importer_addon_named_by_the_project(name):
    analysis_test(
        name = name,
        target = run_view(name + "_run", _FIXTURE, [_FIXTURE + ":uses_importer"]),
        impl = _used_importer_addon_named_by_the_project,
    )

def _used_importer_addon_named_by_the_project(env, target):
    env.expect.that_collection([str(addon.label) for addon in target[GodotViewInfo].addons]).contains_exactly([_label("md_importer")])

# US5 AS4, FR-016: resources that use an add-on with an importer role under a project that
# does not name it fail, naming the resources, the add-on and the project.
def _test_used_unnamed_importer_addon_fails(name):
    failure_test(
        name,
        run_view(name + "_run", _FIXTURE + ":unnamed_project", [_FIXTURE + ":uses_importer"]),
        "*:uses_importer uses the add-on *:md_importer, whose importer role only the project can activate: name it in the project's deps of *:unnamed_project",
    )

# Importer declarations analysis rejects.
def _test_importer_without_editor_part_fails(name):
    godot_addon(name = name + "_addon", importer_suffixes = ["md"], tags = ["manual"])
    failure_test(name, name + "_addon", "*: importer_suffixes needs an editor part with a plugin.cfg or an extension")

def _test_importer_suffix_with_a_dot_fails(name):
    godot_addon(name = name + "_addon", importer_suffixes = [".md"], tags = ["manual"])
    failure_test(name, name + "_addon", "*: importer suffix \".md\" must be a lowercase file suffix without a dot, such as \"md\"")

def _test_import_setting_without_setting_fails(name):
    godot_addon(name = name + "_addon", import_settings = ["md_importer/heading"], tags = ["manual"])
    failure_test(name, name + "_addon", "*: import_settings names md_importer/heading, which is no key of its settings")

def import_plugin_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_import_setting_without_setting_fails,
            _test_import_settings_reach_the_processes_staging_the_importer,
            _test_importer_suffix_with_a_dot_fails,
            _test_importer_without_editor_part_fails,
            _test_initialization_and_export_stage_the_importers_of_their_files,
            _test_only_imports_of_own_md_files_stage_the_importer,
            _test_project_indexes_importers_by_suffix,
            _test_used_importer_addon_named_by_the_project,
            _test_used_unnamed_importer_addon_fails,
        ],
    )
