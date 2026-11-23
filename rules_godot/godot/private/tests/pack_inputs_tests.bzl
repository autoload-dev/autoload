"""
Which pack actions an edit of a resource, a descriptor, test data or a native source reruns.

Each test carries one case of the `resources` and `app` scenarios of
tools/verify_incrementality.py: the edited file or setting is an input of the actions the
case reruns, and no input of the other actions a build of the pack runs.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load(
    ":action_inputs.bzl",
    "build_graph",
    "expect_built_mentions",
    "expect_built_not_read",
    "expect_built_reads",
    "expect_import_lists",
    "expect_mentioned_only_by",
    "expect_not_read",
    "expect_unreached",
    "godot_actions",
)
load(":pack_forms.bzl", "GODOT_EXPORT")

_ASSETS = "//godot/private/tests/fixtures/project_with_imported_assets"
_NATIVE = "//godot/private/tests/fixtures/project_with_native_extension"

def _analysis_test(name, target, impl):
    analysis_test(
        name = name,
        target = target,
        impl = impl,
        # The cases are those of Godot's export; pack_conversion_tests.bzl has the writer's.
        config_settings = GODOT_EXPORT,
        extra_target_under_test_aspects = [godot_actions],
    )

# Besides the pack, the validations of the units whose closure holds a file stage it, the
# class fragment of its unit reads a script, and the pack's reference check scans every
# member; they are validation outputs, which no producing action reads.
_CONTENT_CHECKS = ["GodotClassFragment", "GodotResourceGraph", "GodotValidate"]

def _expect_only_the_pack_reads(env, target, resource_path, other_units):
    graph = build_graph(target)
    expect_built_reads(env, graph, "GodotPack", resource_path)
    expect_built_not_read(env, graph, resource_path, readers = ["GodotPack"] + _CONTENT_CHECKS)

    # The imports of the units that have files with an importer do not stage it.
    for unit in other_units:
        expect_import_lists(env, graph, unit, resource_path, listed = False)

# resources/script_changed: main.gd reruns GodotPack and its unit's content checks only.
def _test_script_reaches_only_the_pack(name):
    _analysis_test(name, _ASSETS + ":pack", _script_reaches_only_the_pack)

def _script_reaches_only_the_pack(env, target):
    _expect_only_the_pack_reads(env, target, "main/main.gd", ["icon", "other"])

# resources/one_asset_changed: icon.svg reruns its own GodotImport, GodotMetadataIndex,
# GodotPack and the pack's reference scan.
def _test_imported_asset_reaches_its_import_metadata_index_and_pack(name):
    _analysis_test(name, _ASSETS + ":pack", _imported_asset_reaches_its_import_metadata_index_and_pack)

def _imported_asset_reaches_its_import_metadata_index_and_pack(env, target):
    graph = build_graph(target)
    expect_import_lists(env, graph, "icon", "main/icon.svg")
    for unit in ["main", "other"]:
        expect_import_lists(env, graph, unit, "main/icon.svg", listed = False)

    # The icon's import result carries its new UIDs to the metadata index and the pack.
    for mnemonic in ["GodotMetadataIndex", "GodotPack"]:
        expect_built_reads(env, graph, mnemonic, "godot/private/tests/fixtures/project_with_imported_assets/icon.import")
    expect_built_not_read(env, graph, "project_with_imported_assets/icon.import", readers = ["GodotMetadataIndex", "GodotPack"])
    expect_built_reads(env, graph, "GodotPack", "main/icon.svg")
    expect_built_not_read(env, graph, "main/icon.svg", readers = ["GodotPack", "GodotResourceGraph"])

# app/script_changed and the pack side of app/app_script_changed: main.gd reruns
# GodotPack only, and not the metadata index.
def _test_script_of_a_project_with_an_extension_reaches_only_the_pack(name):
    _analysis_test(name, _NATIVE + ":pack", _script_of_a_project_with_an_extension_reaches_only_the_pack)

def _script_of_a_project_with_an_extension_reaches_only_the_pack(env, target):
    _expect_only_the_pack_reads(env, target, "main/main.gd", [])

# app/common_resource_changed: common.txt reruns GodotPack and the validations staging it
# only.
def _test_raw_resource_reaches_only_the_pack(name):
    _analysis_test(name, _NATIVE + ":pack", _raw_resource_reaches_only_the_pack)

def _raw_resource_reaches_only_the_pack(env, target):
    _expect_only_the_pack_reads(env, target, "main/common.txt", [])

# app/descriptor_changed: renaming the descriptor's resource path reruns
# GodotMetadataIndex, GodotConfigurationEntries, GodotPack and the pack's reference check.
def _test_descriptor_resource_path_reaches_metadata_index_and_pack(name):
    _analysis_test(name, _NATIVE + ":pack", _descriptor_resource_path_reaches_metadata_index_and_pack)

def _descriptor_resource_path_reaches_metadata_index_and_pack(env, target):
    graph = build_graph(target)
    mentioning = ["GodotConfigurationEntries", "GodotMetadataIndex", "GodotPack", "GodotPackSelection", "GodotResourceGraph"]
    for mnemonic in mentioning:
        expect_built_mentions(env, graph, mnemonic, "native/hello.gdextension")
    expect_mentioned_only_by(env, graph, "native/hello.gdextension", mentioning)

# app/runtime_only: runtime data of a test reruns the test and no Godot action.
def _test_runtime_test_data_reaches_no_godot_action(name):
    _analysis_test(name, _NATIVE + ":runtime_input_test", _runtime_test_data_reaches_no_godot_action)

def _runtime_test_data_reaches_no_godot_action(env, target):
    env.expect.that_target(target).runfiles().contains_predicate(
        matching.str_endswith("project_with_native_extension/tests/runtime_input.txt"),
    )
    expect_not_read(env, target, [], "tests/runtime_input.txt")
    expect_unreached(env, build_graph(target), "tests/runtime_input.txt")

# An extension's native source reruns the export and the shell probe, which load its library
# (D29), and no other Godot action.
def _test_native_source_reaches_only_the_export(name):
    _analysis_test(name, _NATIVE + ":pack", _native_source_reaches_only_the_export)

def _native_source_reaches_only_the_export(env, target):
    graph = build_graph(target)
    readers = ["GodotPack", "GodotShellAssets"]
    expect_built_not_read(env, graph, "native/hello.cc", readers = readers)
    expect_unreached(env, graph, "native/hello.cc", readers = readers)

def pack_inputs_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_descriptor_resource_path_reaches_metadata_index_and_pack,
            _test_imported_asset_reaches_its_import_metadata_index_and_pack,
            _test_native_source_reaches_only_the_export,
            _test_raw_resource_reaches_only_the_pack,
            _test_runtime_test_data_reaches_no_godot_action,
            _test_script_of_a_project_with_an_extension_reaches_only_the_pack,
            _test_script_reaches_only_the_pack,
        ],
    )
