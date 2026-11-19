"""
The test godot_gdunit_test generates: rules_godot's GdUnit adapter as its main script over
the suites targets' own files, and its rejection of a test without suites; and the parts of
the vendored GdUnit4 add-on.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/gdunit:defs.bzl", "godot_gdunit_test")
load("//godot/private:gdunit.bzl", "validate_suites")
load("//godot/private:view.bzl", "GodotViewInfo")
load("//godot/private/tests:manifests.bzl", "manifest_content", "written_content")
load("//godot/private/tests:mocks.bzl", "mocks")
load("//godot/private/tests:views.bzl", "run_view")

_SUITES = "//godot/private/tests/gdunit/fixtures/gdunit_suites"
_ADAPTER = "addons/rules_godot_gdunit/"

def _gdunit(name):
    godot_gdunit_test(
        name = name + "_gdunit",
        project = _SUITES + ":project",
        suites = [_SUITES + ":passing_suites"],
        tags = ["manual"],
    )
    return name + "_gdunit"

# GdUnit's assertions provoke engine errors on purpose, so only the adapter decides.
def _test_gdunit_runs_adapter_over_suites(name):
    test = _gdunit(name)
    analysis_test(
        name = name,
        targets = {"case_list": test + ".case_list", "test": test, "view": test + ".view"},
        impl = _gdunit_runs_adapter_over_suites,
    )

def _gdunit_runs_adapter_over_suites(env, targets):
    manifest = manifest_content(targets.test, ".run.json")
    env.expect.where(field = "main").that_str(manifest["main"]).equals(_ADAPTER + "run.gd")
    env.expect.where(field = "engine_errors").that_str(manifest["engine_errors"]).equals("report")
    members = targets.view[GodotViewInfo].member_resource_paths
    env.expect.that_collection(sorted(members), expr = "member resource paths").contains_at_least([
        _ADAPTER + "run.gd",
        _ADAPTER + "suites.txt",
    ])

    env.expect.where(member = _ADAPTER + "suites.txt").that_collection(
        targets.case_list[DefaultInfo].files.to_list(),
    ).contains_exactly([members[_ADAPTER + "suites.txt"]])

# The suites are the files the suites targets declare, in path order, generated ones
# included; GdUnit's own files, which they depend on, are none.
def _test_suites_are_own_files_including_generated(name):
    test = _gdunit(name)
    analysis_test(name = name, target = test + ".case_list", impl = _suites_are_own_files_including_generated)

# The case list holds the suites targets' own files, generated ones included; the
# adapter keeps those that are GdUnit suites when it runs (FR-032).
def _suites_are_own_files_including_generated(env, target):
    env.expect.that_str(written_content(target, ".txt")).equals(
        "res://passing/GeneratedTest.gd\nres://passing/PassingTest.gd\nres://passing/PassingTest.gd.uid\n" +
        "res://passing/suites/StringTest.gd\nres://passing/support/Totals.gd\n",
    )

_GDUNIT4_EDITOR_SCENES = [
    "addons/gdUnit4/src/network/GdUnitServer.tscn",
    "addons/gdUnit4/src/ui/GdUnitConsole.tscn",
    "addons/gdUnit4/src/ui/GdUnitInspector.tscn",
]

# The scenes GdUnit's editor plugin docks belong to its editor part, never to the members.
# This pins the declaration; gdunit4_pack_leaves_out_editor_scenes_test checks the pack.
def _test_gdunit4_docked_scenes_are_editor_part(name):
    analysis_test(
        name = name,
        target = run_view(name + "_run", _SUITES + ":project", ["@gdunit4"]),
        impl = _gdunit4_docked_scenes_are_editor_part,
    )

def _gdunit4_docked_scenes_are_editor_part(env, target):
    view = target[GodotViewInfo]
    members = env.expect.where(field = "member_resource_paths").that_collection(view.member_resource_paths.keys())
    members.contains("addons/gdUnit4/src/GdUnitTestSuite.gd")
    members.contains_none_of(_GDUNIT4_EDITOR_SCENES)
    env.expect.where(field = "editor_resource_paths").that_collection(
        view.editor_resource_paths.keys(),
    ).contains_at_least(_GDUNIT4_EDITOR_SCENES)

def _test_gdunit_without_suites_fails(env):
    errors, fail_ = mocks.errors()
    validate_suites("unit_tests", [], _fail = fail_)
    validate_suites("unit_tests", [":unit_suites"], _fail = fail_)
    env.expect.that_collection(errors).contains_exactly([
        "unit_tests: godot_gdunit_test requires at least one suites target",
    ])

def gdunit_adapter_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_gdunit_runs_adapter_over_suites,
            _test_suites_are_own_files_including_generated,
            _test_gdunit4_docked_scenes_are_editor_part,
        ],
        basic_tests = [
            _test_gdunit_without_suites_fails,
        ],
    )
