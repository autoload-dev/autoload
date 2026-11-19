"""
Which operations share the import of a unit: those of one project, across the platform slices
of a pack, and none of two projects. Across target configurations, the unit's actions differ
only in the configuration of their paths, which path mapping removes from their cache keys.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:paths.bzl", "mapped_path")
load(":action_inputs.bzl", "GodotActionsInfo", "godot_actions", "import_manifests", "mapped_cache_keys")
load(":pack_actions.bzl", "PackActionsInfo", "pack_actions")
load(":packaging.bzl", "in_export_platform")

_FIXTURE = "//godot/private/tests/fixtures/project_with_shared_unit"

def _expect_one_import(env, target, subject, unit):
    """Assert that a target reaches one import of the unit and return its manifests."""
    manifests = import_manifests(target, unit)
    env.expect.where(operation = subject, unit = unit).that_collection(manifests).has_size(1)
    return manifests

# SC-001: a pack and two tests of one project whose selections share :base and
# :home import each with one manifest. The tests run in the editor variant, so each unit
# declares an import there and one beside the pack; path mapping gives them one cache key.
def _test_operations_of_one_project_share_each_import(name):
    analysis_test(
        name = name,
        targets = {
            "home_test": _FIXTURE + ":home_test",
            "pack": _FIXTURE + ":pack",
            "test": _FIXTURE + ":test",
        },
        impl = _operations_of_one_project_share_each_import,
        extra_target_under_test_aspects = [godot_actions],
    )

def _operations_of_one_project_share_each_import(env, targets):
    for unit in ["base", "home"]:
        imports = {}
        for subject in ["home_test", "pack", "test"]:
            for manifest in _expect_one_import(env, getattr(targets, subject), subject, unit).values():
                imports[json.encode(manifest)] = manifest
        env.expect.where(unit = unit).that_collection(imports).has_size(1)
        for manifest in imports.values():
            env.expect.where(unit = unit).that_str(manifest["project_file"]).contains("/project.import.project.godot")

# The same units under two projects import once per project, each under its project's
# import configuration.
def _test_two_projects_import_a_unit_separately(name):
    analysis_test(
        name = name,
        targets = {
            "home_test": _FIXTURE + ":home_test",
            "other_home_test": _FIXTURE + ":other_home_test",
        },
        impl = _two_projects_import_a_unit_separately,
        extra_target_under_test_aspects = [godot_actions],
    )

def _two_projects_import_a_unit_separately(env, targets):
    for unit in ["base", "home"]:
        configurations = []
        for subject in ["home_test", "other_home_test"]:
            manifests = _expect_one_import(env, getattr(targets, subject), subject, unit)
            configurations.extend([manifest["project_file"].rpartition("/")[2] for manifest in manifests.values()])
        env.expect.where(unit = unit).that_collection(configurations).contains_exactly([
            "other_project.import.project.godot",
            "project.import.project.godot",
        ])

# A pack exported for a platform of two slices reaches its native path once per slice and
# imports each unit once: the slices share the import, and the native path, where the
# context is reset, declares none.
def _test_platform_slices_of_a_pack_share_each_import(name):
    analysis_test(
        name = name,
        target = _FIXTURE + ":home_pack",
        impl = _platform_slices_of_a_pack_share_each_import,
        extra_target_under_test_aspects = [godot_actions, pack_actions],
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/private/config/tests:android_distribution")),
        },
    )

def _platform_slices_of_a_pack_share_each_import(env, target):
    env.expect.that_int(target[PackActionsInfo].native_slices, expr = "configured native paths").equals(2)
    for unit in ["base", "home"]:
        for manifest in _expect_one_import(env, target, "pack", unit).values():
            env.expect.where(unit = unit).that_str(manifest["project_file"]).contains("/other_project.import.project.godot")

# The actions that support path mapping, besides the imports: analysis does not show an
# import, which expands from a template once Godot's importable suffixes are known.
_MAPPED_MNEMONICS = ["GodotClassFragment", "GodotImportFeatures", "GodotImportableSuffixes", "GodotValidate"]

# What an import reads besides its staged files.
_IMPORT_MANIFESTS = (".import.json", ".resource_paths.json", ".import_scripts.json")

def _cache_keys(target):
    """Return the cache keys of a target's mapped actions under path mapping, and its import manifests."""
    keys = {
        (owner, "import", (mapped,)): content
        for suffix in _IMPORT_MANIFESTS
        for owner, mapped, content in _written(target, suffix)
    }
    keys.update(mapped_cache_keys(target, _MAPPED_MNEMONICS))
    return keys

def _written(target, suffix):
    return [
        (entry.owner, mapped_path(entry.action.outputs.to_list()[0]), entry.action.content)
        for entry in target[GodotActionsInfo].every.to_list()
        if entry.action.mnemonic == "FileWrite" and entry.action.outputs.to_list()[0].basename.endswith(suffix)
    ]

# A host test and a pack for Android analyze the same project and units in two target
# configurations. Each of their imports, class fragments, validations and import probes has
# the same command line, inputs and manifests once path mapping removes the configuration
# from output paths, so the two share one result of each.
def _test_target_configurations_share_each_unit_action(name):
    in_export_platform(
        name = name + "_android_pack",
        export_platform = "//godot/platforms:android_arm64",
        tags = ["manual"],
        deps = [_FIXTURE + ":home_pack"],
    )
    analysis_test(
        name = name,
        targets = {
            "android_pack": ":%s_android_pack" % name,
            "test": _FIXTURE + ":other_home_test",
        },
        impl = _target_configurations_share_each_unit_action,
        extra_target_under_test_aspects = [godot_actions],
    )

def _target_configurations_share_each_unit_action(env, targets):
    test = _cache_keys(targets.test)
    pack = _cache_keys(targets.android_pack)
    for kind in _MAPPED_MNEMONICS + ["import"]:
        env.expect.where(kind = kind).that_bool(
            any([key[1] == kind for key in test]),
            expr = "the test reaches it",
        ).equals(True)
    env.expect.that_collection(sorted(pack.keys()), expr = "mapped actions").contains_exactly(sorted(test.keys()))
    for key, facts in test.items():
        env.expect.where(action = str(key)).that_str(pack.get(key, "")).equals(facts)

def import_sharing_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_operations_of_one_project_share_each_import,
            _test_platform_slices_of_a_pack_share_each_import,
            _test_target_configurations_share_each_unit_action,
            _test_two_projects_import_a_unit_separately,
        ],
    )
