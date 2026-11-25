"""
What each value of the metadata flags does: whether an operation's view indexes the metadata
its files lack, whether a pack assigns node IDs and resource UIDs in its copy, whether it checks them
in the checkout, and whether godot_metadata_sync writes them back.

Each test sets both //godot/metadata flags, node_ids and resource_uids, to one value.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot/private:view.bzl", "GodotViewInfo")
load(":pack_actions.bzl", "PackActionsInfo", "pack_actions", "pack_manifest")
load(":views.bzl", "run_view")

_FIXTURE = "//godot/private/tests/fixtures/import_context"
_KINDS = ["node_ids", "resource_uids"]
_CHECKS = ["GodotNodeIds", "GodotResourceUids"]

def _metadata_flags(value):
    return {str(Label("//godot/metadata:" + kind)): value for kind in _KINDS}

def _pack_test(name, value, impl):
    analysis_test(
        name = name,
        target = _FIXTURE + ":members_pack",
        impl = impl,
        config_settings = _metadata_flags(value),
        extra_target_under_test_aspects = [pack_actions],
    )

def _project_test(name, value, impl):
    analysis_test(
        name = name,
        target = run_view(
            name + "_run",
            _FIXTURE,
            [_FIXTURE + ":configured_check", _FIXTURE + ":configured_resources"],
        ),
        impl = impl,
        config_settings = _metadata_flags(value),
    )

def _assigned_kinds(target):
    return pack_manifest(target).get("metadata_index", {}).get("assign", [])

def _checks(target):
    return sorted([action.mnemonic for action in target[PackActionsInfo].actions if action.mnemonic in _CHECKS])

def _written_kinds(target):
    listing = [action for action in target[TestingAspectInfo].actions if action.mnemonic == "GodotMetadata"][0]
    return [kind for kind in _KINDS if kind in listing.argv]

def _expect_pack_assigns_both_kinds(env, target):
    env.expect.that_collection(_assigned_kinds(target), expr = "assigned metadata").contains_exactly(_KINDS).in_order()

def _expect_pack_assigns_nothing(env, target):
    env.expect.that_collection(_assigned_kinds(target), expr = "assigned metadata").contains_exactly([])

def _expect_pack_checks_both_kinds(env, target):
    env.expect.that_collection(_checks(target), expr = "checkout checks").contains_exactly(_CHECKS).in_order()

def _expect_pack_checks_nothing(env, target):
    env.expect.that_collection(_checks(target), expr = "checkout checks").contains_exactly([])

def _expect_sync_writes_both_kinds(env, target):
    env.expect.that_collection(_written_kinds(target), expr = "written metadata").contains_exactly(_KINDS).in_order()

def _expect_sync_writes_nothing(env, target):
    env.expect.that_collection(_written_kinds(target), expr = "written metadata").contains_exactly([])

# The view indexes the metadata its files lack only when a flag asks for metadata.
def _expect_project_indexes_nothing(env, target):
    env.expect.where(field = "metadata_index").that_bool(
        target[GodotViewInfo].metadata_index == None,
    ).equals(True)

def _expect_project_declares_index(env, target):
    index = target[GodotViewInfo].metadata_index
    env.expect.where(field = "metadata_index").that_str(index.basename if index else "").equals(
        target.label.name + ".metadata_index.json",
    )
    env.expect.where(field = "metadata_index").that_str(str(index.owner) if index else "").equals(str(target.label))

def _test_off_metadata_project_indexes_nothing(name):
    _project_test(name, "off", _expect_project_indexes_nothing)

def _test_assign_metadata_project_declares_index(name):
    _project_test(name, "assign", _expect_project_declares_index)

def _test_off_metadata_pack_assigns_nothing(name):
    _pack_test(name, "off", _expect_pack_assigns_nothing)

def _test_off_metadata_pack_checks_nothing(name):
    _pack_test(name, "off", _expect_pack_checks_nothing)

def _test_off_metadata_sync_writes_nothing(name):
    _project_test(name, "off", _expect_sync_writes_nothing)

def _test_assign_metadata_pack_assigns_both_kinds(name):
    _pack_test(name, "assign", _expect_pack_assigns_both_kinds)

def _test_assign_metadata_pack_checks_nothing(name):
    _pack_test(name, "assign", _expect_pack_checks_nothing)

def _test_assign_metadata_sync_writes_nothing(name):
    _project_test(name, "assign", _expect_sync_writes_nothing)

def _test_sync_metadata_pack_assigns_both_kinds(name):
    _pack_test(name, "sync", _expect_pack_assigns_both_kinds)

def _test_sync_metadata_pack_checks_nothing(name):
    _pack_test(name, "sync", _expect_pack_checks_nothing)

def _test_sync_metadata_sync_writes_both_kinds(name):
    _project_test(name, "sync", _expect_sync_writes_both_kinds)

def _test_require_metadata_pack_assigns_both_kinds(name):
    _pack_test(name, "require", _expect_pack_assigns_both_kinds)

def _test_require_metadata_pack_checks_both_kinds(name):
    _pack_test(name, "require", _expect_pack_checks_both_kinds)

def _test_require_metadata_sync_writes_both_kinds(name):
    _project_test(name, "require", _expect_sync_writes_both_kinds)

def metadata_policy_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_assign_metadata_pack_assigns_both_kinds,
            _test_assign_metadata_pack_checks_nothing,
            _test_assign_metadata_project_declares_index,
            _test_assign_metadata_sync_writes_nothing,
            _test_off_metadata_pack_assigns_nothing,
            _test_off_metadata_pack_checks_nothing,
            _test_off_metadata_project_indexes_nothing,
            _test_off_metadata_sync_writes_nothing,
            _test_require_metadata_pack_assigns_both_kinds,
            _test_require_metadata_pack_checks_both_kinds,
            _test_require_metadata_sync_writes_both_kinds,
            _test_sync_metadata_pack_assigns_both_kinds,
            _test_sync_metadata_pack_checks_nothing,
            _test_sync_metadata_sync_writes_both_kinds,
        ],
    )
