"""
Which actions an edit of the project file, an export option or a pack's membership reruns.

Each test carries one case of tools/verify_capabilities.py: the edited file or setting is
an input of the actions the case reruns, and no input of the other actions a build of the
pack runs.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load(":action_inputs.bzl", "expect_not_read", "godot_actions")
load(":built_graph.bzl", "build_graph", "expect_built_mentions", "expect_built_not_read", "expect_built_reads", "expect_built_reads_output_of", "expect_mentioned_only_by", "expect_not_built")
load(":pack_forms.bzl", "GODOT_EXPORT")

visibility("private")

_ASSETS = "//godot/private/tests/fixtures/project_with_imported_assets"
_MEMBERSHIP = "//godot/private/tests/fixtures/project_with_pack_membership"

def _analysis_test(name, target, impl):
    analysis_test(
        name = name,
        target = target,
        impl = impl,
        # The cases are those of Godot's export; pack_conversion_tests.bzl has the writer's.
        config_settings = GODOT_EXPORT,
        extra_target_under_test_aspects = [godot_actions],
    )

# runtime_purpose_configuration: emptying project.godot's main scene reruns
# GodotExportConfig, GodotImportConfig, GodotImportFeatures, GodotConfigurationEntries,
# which resolves the authored entries, GodotAuthoredAutoloads, GodotPack and
# GodotProjectConfig, whose runtime configuration the pack's reference scan reads, and no
# GodotImport or GodotValidate. The import reads only GodotImportConfig's output, which
# omits the main scene (project_config_test.py,
# test_runtime_only_changes_do_not_change_the_import_configuration), and the validation
# GodotAuthoredAutoloads' too, which lists only the autoloads.
def _test_project_file_reaches_configurations_and_pack_but_no_import(name):
    _analysis_test(name, _ASSETS + ":pack", _project_file_reaches_configurations_and_pack_but_no_import)

def _project_file_reaches_configurations_and_pack_but_no_import(env, target):
    graph = build_graph(target)
    project_file = "project_with_imported_assets/project.godot"
    readers = ["GodotAuthoredAutoloads", "GodotConfigurationEntries", "GodotExportConfig", "GodotImportConfig", "GodotImportFeatures", "GodotProjectConfig"]
    for mnemonic in readers:
        expect_built_reads(env, graph, mnemonic, project_file)
    expect_built_reads_output_of(env, graph, "GodotPack", "GodotExportConfig")
    expect_built_reads_output_of(env, graph, "GodotResourceGraph", "GodotProjectConfig")
    expect_built_reads_output_of(env, graph, "GodotValidate", "GodotAuthoredAutoloads")
    expect_built_not_read(env, graph, project_file, readers = readers)

# export_options: changing preset_settings' script_export_mode reruns GodotPack only.
def _test_script_export_mode_reaches_only_the_pack(name):
    _analysis_test(name, _ASSETS + ":pack", _script_export_mode_reaches_only_the_pack)

def _script_export_mode_reaches_only_the_pack(env, target):
    graph = build_graph(target)
    expect_built_mentions(env, graph, "GodotPack", "\"script_export_mode\":\"0\"")
    expect_mentioned_only_by(env, graph, "script_export_mode", ["GodotPack"])

# unselected_resources: the red pack's brand file reruns nothing of the blue pack.
def _test_unselected_resource_reaches_no_action_of_another_pack(name):
    _analysis_test(name, _MEMBERSHIP + ":blue_pack", _unselected_resource_reaches_no_action_of_another_pack)

def _unselected_resource_reaches_no_action_of_another_pack(env, target):
    expect_not_read(env, target, [], "main/red.json")
    expect_mentioned_only_by(env, build_graph(target), "main/red.json", [])

# shared_resources: a script shared through a dependency reruns GodotPack, the pack's
# reference scan and its own unit's class fragment, interface and content check only; the
# content checks of the units depending on it read its interface.
def _test_shared_script_reaches_only_the_pack(name):
    _analysis_test(name, _MEMBERSHIP + ":blue_pack", _shared_script_reaches_only_the_pack)

def _shared_script_reaches_only_the_pack(env, target):
    graph = build_graph(target)
    expect_built_reads(env, graph, "GodotPack", "main/shared/math.gd")
    expect_built_not_read(
        env,
        graph,
        "main/shared/math.gd",
        readers = ["GodotClassFragment", "GodotPack", "GodotResourceGraph", "GodotUnitInterface", "GodotValidate"],
    )

# test_only_source: a script only a test uses reruns nothing of the pack.
def _test_test_only_script_reaches_no_pack_action(name):
    _analysis_test(name, _MEMBERSHIP + ":blue_pack", _test_only_script_reaches_no_pack_action)

def _test_only_script_reaches_no_pack_action(env, target):
    expect_not_read(env, target, [], "tests/math_test.gd")
    expect_mentioned_only_by(env, build_graph(target), "tests/math_test.gd", [])

# dynamic_membership: a new file of a globbed resource target reruns
# GodotMetadataIndex, GodotConfigurationEntries and the pack's reference check, whose
# manifests list every member, and GodotPack; edits of existing members leave the first
# two current. An existing member of the
# glob stands for the new one.
def _test_new_member_reaches_metadata_index_and_pack(name):
    _analysis_test(name, _MEMBERSHIP + ":blue_pack", _new_member_reaches_metadata_index_and_pack)

def _new_member_reaches_metadata_index_and_pack(env, target):
    graph = build_graph(target)
    member = "main/levels/one.json"
    mentioning = ["GodotConfigurationEntries", "GodotMetadataIndex", "GodotPack", "GodotPackSelection", "GodotResourceGraph"]
    for mnemonic in mentioning:
        expect_built_mentions(env, graph, mnemonic, "\"%s\"" % member)
    expect_mentioned_only_by(env, graph, "\"%s\"" % member, mentioning)
    for mnemonic in ["GodotPack", "GodotResourceGraph"]:
        expect_built_reads(env, graph, mnemonic, member)
    expect_built_not_read(env, graph, member, readers = ["GodotPack", "GodotResourceGraph"])

# unreachable_member: editing a member no entry point reaches reruns the project's
# GodotResourceGraph and GodotPack, which declares every project file; the selection
# reads only the graph, whose references are unchanged.
def _test_unreachable_member_reaches_resource_graph_and_pack(name):
    _analysis_test(name, _MEMBERSHIP + ":base_pack", _unreachable_member_reaches_resource_graph_and_pack)

def _unreachable_member_reaches_resource_graph_and_pack(env, target):
    graph = build_graph(target)
    member = "main/levels/two.json"
    readers = ["GodotPack", "GodotResourceGraph"]
    for mnemonic in readers:
        expect_built_reads(env, graph, mnemonic, member)
    expect_built_reads_output_of(env, graph, "GodotPackSelection", "GodotResourceGraph")
    expect_built_not_read(env, graph, member, readers = readers)

# required_pack_selection: changing the required pack's entry_points reruns its
# GodotPackSelection and the dependent pack's, which reads the required pack's
# selection; a build of the dependent pack runs no export of the required pack.
def _test_required_pack_entry_points_reach_both_selections(name):
    _analysis_test(name, _MEMBERSHIP + ":dlc_pack", _required_pack_entry_points_reach_both_selections)

def _required_pack_entry_points_reach_both_selections(env, target):
    graph = build_graph(target)
    expect_built_mentions(env, graph, "GodotPackSelection", "\"entry_points\":[]", owner = "base_pack.export")
    expect_built_reads_output_of(
        env,
        graph,
        "GodotPackSelection",
        "GodotPackSelection",
        owner = "dlc_pack.export",
        producer_owner = "base_pack.export",
        producing = "base_pack.content.json",
    )
    expect_mentioned_only_by(env, graph, "\"entry_points\"", ["GodotPackSelection"])
    expect_not_built(env, graph, "GodotPack", owner = "base_pack.export")

def pack_selection_inputs_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_new_member_reaches_metadata_index_and_pack,
            _test_project_file_reaches_configurations_and_pack_but_no_import,
            _test_required_pack_entry_points_reach_both_selections,
            _test_script_export_mode_reaches_only_the_pack,
            _test_shared_script_reaches_only_the_pack,
            _test_test_only_script_reaches_no_pack_action,
            _test_unreachable_member_reaches_resource_graph_and_pack,
            _test_unselected_resource_reaches_no_action_of_another_pack,
        ],
    )
