"""
How packs scan their members' references, and which entry points a pack accepts.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:defs.bzl", "godot_pack")
load("//godot/private/tests:pack_forms.bzl", "GODOT_EXPORT")
load(":action_inputs.bzl", "build_graph", "expect_built_not_read", "expect_built_reads_output_of", "godot_actions")
load(":expected_failures.bzl", "failure_test")

_FIXTURE = "//godot/private/tests/fixtures/import_context"
_CONFIGURED = [_FIXTURE + ":configured_check", _FIXTURE + ":configured_resources"]

# Every pack scans its members' references, which its selection checks. A pack of all
# members runs that check beside the export, which reads nothing of it.
def _test_members_pack_checks_references_beside_the_export(name):
    analysis_test(
        name = name,
        target = _FIXTURE + ":members_pack",
        impl = _members_pack_checks_references_beside_the_export,
        extra_target_under_test_aspects = [godot_actions],
    )

def _members_pack_checks_references_beside_the_export(env, target):
    graph = build_graph(target)
    expect_built_reads_output_of(env, graph, "GodotPackSelection", "GodotResourceGraph")
    expect_built_not_read(env, graph, "members_pack.selection.json")

def _test_reachable_pack_scans_references(name):
    godot_pack(
        name = name + "_pack",
        preset_settings = {"script_export_mode": "0"},
        project = _FIXTURE,
        packing = "reachable",
        tags = ["manual"],
        deps = _CONFIGURED,
    )
    analysis_test(
        name = name,
        target = name + "_pack",
        impl = _reachable_pack_scans_references,
        config_settings = GODOT_EXPORT,
        extra_target_under_test_aspects = [godot_actions],
    )

def _reachable_pack_scans_references(env, target):
    graph = build_graph(target)
    expect_built_reads_output_of(env, graph, "GodotPackSelection", "GodotResourceGraph")
    expect_built_reads_output_of(env, graph, "GodotPack", "GodotPackSelection")

def _test_entry_points_without_reachable_selection_fail(name):
    godot_pack(
        name = name + "_pack",
        entry_points = ["main/configured_test.gd"],
        preset_settings = {"script_export_mode": "0"},
        project = _FIXTURE,
        tags = ["manual"],
        deps = _CONFIGURED,
    )
    failure_test(name, name + "_pack", 'entry_points require packing = "reachable"')

def _test_undeclared_entry_point_fails(name):
    godot_pack(
        name = name + "_pack",
        entry_points = ["absent.gd"],
        preset_settings = {"script_export_mode": "0"},
        project = _FIXTURE,
        packing = "reachable",
        tags = ["manual"],
        deps = _CONFIGURED,
    )
    failure_test(name, name + "_pack", "Entry point res://absent.gd is not a declared project member")

def pack_selection_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_entry_points_without_reachable_selection_fail,
            _test_members_pack_checks_references_beside_the_export,
            _test_reachable_pack_scans_references,
            _test_undeclared_entry_point_fails,
        ],
    )
