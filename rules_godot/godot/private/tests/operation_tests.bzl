"""What an operation works on: the project it names and the resources it lists."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:defs.bzl", "godot_test")
load("//godot/private:providers.bzl", "GodotResourcesInfo")
load(":action_inputs.bzl", "GodotActionsInfo", "godot_actions", "source_inputs")

_CONTEXT = "//godot/private/tests/fixtures/import_context"
_SHARED = "//godot/private/tests/fixtures/project_with_shared_unit"
_FIXTURES = "godot/private/tests/fixtures/"

# FR-004, US2: a test in a subpackage that names the project and its package's resources
# reads, of all fixture files, only those resources' files and the project file; no file
# of the project's own package or another package is an input of any of its actions.
def _test_operation_of_one_package_reads_nothing_of_another(name):
    godot_test(
        name = name + "_test",
        size = "small",
        project = _CONTEXT + ":configured_project",
        tags = ["manual"],
        deps = [_CONTEXT + "/main/shared"],
    )
    analysis_test(
        name = name,
        targets = {
            "operation": name + "_test",
            "shared": _CONTEXT + "/main/shared",
        },
        impl = _operation_of_one_package_reads_nothing_of_another,
        extra_target_under_test_aspects = [godot_actions],
    )

def _operation_of_one_package_reads_nothing_of_another(env, targets):
    declared = {file.short_path: True for file in targets.shared[GodotResourcesInfo].member_resource_paths.values()}
    declared[Label(_CONTEXT).package + "/project.godot"] = True
    read = source_inputs([entry.action for entry in targets.operation[GodotActionsInfo].every.to_list()], _FIXTURES)
    env.expect.that_collection(read, expr = "fixture files the test's actions read").contains_exactly(sorted(declared))

# FR-004: a test of an exported pack names no project; it declares no view of its own and
# runs no action under a context, only those of the pack it names.
def _test_test_of_a_pack_names_no_project(name):
    godot_test(
        name = name + "_test",
        size = "small",
        pack = _SHARED + ":pack",
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = name + "_test",
        impl = _test_of_a_pack_names_no_project,
        extra_target_under_test_aspects = [godot_actions],
    )

def _test_of_a_pack_names_no_project(env, target):
    package = str(target.label).rpartition(":")[0] + ":"
    owners = {entry.owner: True for entry in target[GodotActionsInfo].every.to_list() if entry.owner.startswith(package)}
    env.expect.that_collection(sorted(owners), expr = "owners of actions in the test's package").contains_exactly([str(target.label)])
    initializations = [entry.owner for entry in target[GodotActionsInfo].actions.to_list() if entry.action.mnemonic == "GodotInitialize"]
    env.expect.that_collection(initializations, expr = "owners of GodotInitialize").contains_exactly([str(Label(_SHARED + ":pack.view"))])

def operation_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_operation_of_one_package_reads_nothing_of_another,
            _test_test_of_a_pack_names_no_project,
        ],
    )
