"""
The godot_actions aspect reaches the Godot actions of a pack's dependency graph, and which
edits rerun an import.

Analysis does not show an import itself (action_inputs.bzl); what it stages is what the
manifests analysis writes for it list: `<unit>.resource_paths.json` of each unit in its
closure, `<unit>.import_scripts.json` of its import inputs, and the import configuration.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load(":action_inputs.bzl", "expect_not_read", "godot_actions", "mnemonics_of", "written_manifests")
load(":pack_forms.bzl", "GODOT_EXPORT")

_SHARED = "//godot/private/tests/fixtures/project_with_shared_unit"

def _test_pack_reaches_its_godot_actions(name):
    analysis_test(
        name = name,
        target = "//godot/private/tests/fixtures/minimal_project:pack",
        impl = _pack_reaches_its_godot_actions,
        config_settings = GODOT_EXPORT,
        extra_target_under_test_aspects = [godot_actions],
    )

def _pack_reaches_its_godot_actions(env, target):
    env.expect.that_collection(mnemonics_of(target)).contains("GodotPack")

def _staged_by_imports(target):
    """The resource paths and execution paths of every file an import the target reaches stages."""
    staged = {}
    for suffix in [".resource_paths.json", ".import_scripts.json"]:
        for manifest in written_manifests(target, suffix).values():
            staged.update(manifest)
    return staged

# SC-002 on both sides, for a pack and two tests of one project: an imported file
# and an import input are staged by imports, so their edits rerun them; the autoload
# script, the main scene and the extension, whose library its native source builds, are
# staged by none, and the import configuration names neither the autoload nor the main
# scene, so their edits rerun no import.
def _test_program_entries_and_native_sources_reach_no_import(name):
    analysis_test(
        name = name,
        targets = {
            "home_test": _SHARED + ":home_test",
            "pack": _SHARED + ":pack",
            "test": _SHARED + ":test",
        },
        impl = _program_entries_and_native_sources_reach_no_import,
        extra_target_under_test_aspects = [godot_actions],
    )

def _program_entries_and_native_sources_reach_no_import(env, targets):
    for subject in ["home_test", "pack", "test"]:
        target = getattr(targets, subject)
        staged = _staged_by_imports(target)
        for path in ["main/icon.svg", "main/home.svg", "main/home_buffer.bin"]:
            env.expect.where(operation = subject, path = path).that_bool(path in staged, expr = "staged by an import").equals(True)
        for path in ["main/home.gd", "main/state.gd", "main/main.tscn", "native/hello.gdextension"]:
            env.expect.where(operation = subject, path = path).that_bool(path in staged, expr = "staged by an import").equals(False)
        for path in staged.values():
            env.expect.where(operation = subject, path = path).that_bool(
                "/native/" in path or path.endswith(".cc"),
                expr = "an extension file staged by an import",
            ).equals(False)
        configurations = written_manifests(target, "project.import.config.json").values()
        env.expect.where(operation = subject).that_collection(configurations).has_size(1)
        for configuration in configurations:
            env.expect.where(operation = subject).that_dict(configuration["autoloads"]).contains_exactly({})
            for path in ["main/state.gd", "main/main.tscn"]:
                env.expect.where(operation = subject, path = path).that_bool(
                    path in json.encode(configuration),
                    expr = "named by the import configuration",
                ).equals(False)

# SC-002's editor-part case (US1 AS3, FR-019, D29): the editor part of an add-on the
# project names registers an export plugin, which no export runs; no import, initialization,
# export or shell probe reads it, so its edits rerun none of them.
_EDITOR_PART = "godot/private/tests/fixtures/project_with_shared_unit/export_marker/export_marker.gd"

def _test_editor_part_reaches_no_build_process(name):
    analysis_test(
        name = name,
        targets = {
            "home_test": _SHARED + ":home_test",
            "pack": _SHARED + ":pack",
            "test": _SHARED + ":test",
        },
        impl = _editor_part_reaches_no_build_process,
        extra_target_under_test_aspects = [godot_actions],
    )

def _editor_part_reaches_no_build_process(env, targets):
    for subject in ["home_test", "pack", "test"]:
        target = getattr(targets, subject)
        staged = _staged_by_imports(target)
        env.expect.where(operation = subject).that_bool(
            [path for path in staged.values() if path.endswith(_EDITOR_PART)] != [],
            expr = "editor part staged by an import",
        ).equals(False)
        expect_not_read(env, target, ["GodotInitialize", "GodotPack", "GodotShellAssets"], _EDITOR_PART)

def action_inputs_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_editor_part_reaches_no_build_process,
            _test_pack_reaches_its_godot_actions,
            _test_program_entries_and_native_sources_reach_no_import,
        ],
    )
