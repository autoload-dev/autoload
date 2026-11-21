"""
Where add-ons and resources place files of another repository and package: relative to the
package of the target that lists them, and at explicit resource paths.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:providers.bzl", "GodotAddonInfo", "GodotResourcesInfo")
load(":expected_failures.bzl", "failure_test")

_FIXTURE = "//godot/private/tests/fixtures/external_files"

def _test_addon_places_another_repositorys_files(name):
    analysis_test(name = name, target = _FIXTURE + ":vendor", impl = _addon_places_another_repositorys_files)

def _addon_places_another_repositorys_files(env, target):
    addon = target[GodotAddonInfo]
    env.expect.where(part = "runtime").that_collection(sorted(addon.runtime_files.member_resource_paths)).contains_exactly([
        "addons/vendor/runtime/vendor.gd",
        "addons/vendor/settings/vendor.cfg",
    ])
    env.expect.where(part = "editor").that_collection(sorted(addon.editor_files.member_resource_paths)).contains_exactly([
        "addons/vendor/editor/plugin.cfg",
        "addons/vendor/editor/plugin.gd",
    ])
    env.expect.that_str(addon.plugin_config).equals("addons/vendor/editor/plugin.cfg")

def _test_addon_editor_part_at_explicit_paths(name):
    analysis_test(name = name, target = _FIXTURE + ":renamed", impl = _addon_editor_part_at_explicit_paths)

def _addon_editor_part_at_explicit_paths(env, target):
    addon = target[GodotAddonInfo]
    env.expect.that_collection(sorted(addon.editor_files.member_resource_paths)).contains_exactly([
        "addons/renamed/plugin.cfg",
        "addons/renamed/plugin.gd",
    ])
    env.expect.that_collection(addon.runtime_files.member_resource_paths).has_size(0)

def _test_resources_place_files_relative_to_their_target_package(name):
    analysis_test(name = name, target = _FIXTURE + ":values", impl = _resources_place_files_relative_to_their_target_package)

def _resources_place_files_relative_to_their_target_package(env, target):
    env.expect.that_collection(sorted(target[GodotResourcesInfo].member_resource_paths)).contains_exactly([
        "content/local.gd",
        "content/values/default.tres",
    ])

def _test_resource_path_outside_the_addon_directory_fails(name):
    failure_test(
        name,
        _FIXTURE + ":resource_path_outside_directory",
        "*res://settings/vendor.cfg is outside res://addons/resource_path_outside_directory/*",
    )

def _test_file_outside_its_target_package_fails(name):
    failure_test(
        name,
        _FIXTURE + ":file_outside_its_target_package",
        "*addons/vendor/plugin_settings.cfg is outside \"data/\" of *external_release//data:foreign;*; list the files through a target in their own package*",
    )

def external_files_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_addon_editor_part_at_explicit_paths,
            _test_addon_places_another_repositorys_files,
            _test_file_outside_its_target_package_fails,
            _test_resource_path_outside_the_addon_directory_fails,
            _test_resources_place_files_relative_to_their_target_package,
        ],
    )
