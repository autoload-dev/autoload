"""Invocation overrides: --extra_toolchains prioritizes complete or single-role sets.

A complete registration set, or one role only, takes priority over the registered hub; the other
role keeps the hub's component.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private/tests:engines.bzl", "ResolvedInfo")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

_FIXTURES = "//godot/engine/private/tests/fixtures"
_PLATFORMS = "//godot/engine/private/tests:"
_PROBE = "//godot/engine/private/tests:probe"

def _settings(sets = [], execution_platform = None):
    settings = {
        "//command_line_option:platforms": str(Label(_PLATFORMS + "linux_x86_64")),
        str(Label("//godot:variant")): "release",
    } | own_toolchains(sets, [_PLATFORMS + execution_platform] if execution_platform else None)
    return settings

def _resolved(env, target, role):
    resolved = getattr(target[ResolvedInfo], role)
    env.expect.that_bool(resolved != None, "the %s must resolve" % role).equals(True)
    return resolved

def _expect_package(env, target, role, package):
    resolved = _resolved(env, target, role)
    if resolved:
        env.expect.that_str(Label(resolved.provenance.component).package).equals(package)

def _expect_hub(env, target, role):
    resolved = _resolved(env, target, role)
    if resolved:
        # The root module registers the prebuilt hub @godot.
        env.expect.that_str(Label(resolved.provenance.component).package).equals("toolchains")
        env.expect.that_bool(
            Label(resolved.provenance.component).repo_name.endswith("godot"),
            "the %s component's repository ends in godot" % role,
        ).equals(True)

def _test_registered_hub_supplies_both_roles(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_registered_hub_supplies_both_roles_impl,
        config_settings = _settings(),
    )

def _test_registered_hub_supplies_both_roles_impl(env, target):
    _expect_hub(env, target, "editor")
    _expect_hub(env, target, "runtime")

def _test_complete_set_overrides_both_roles(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_complete_set_overrides_both_roles_impl,
        config_settings = _settings([_FIXTURES + ":all"], execution_platform = "linux_arm64"),
    )

def _test_complete_set_overrides_both_roles_impl(env, target):
    fixtures = Label(_FIXTURES + ":all").package
    _expect_package(env, target, "editor", fixtures)
    _expect_package(env, target, "runtime", fixtures)

def _test_editor_only_set_overrides_editor(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_editor_only_set_overrides_editor_impl,
        config_settings = _settings([_FIXTURES + "/editor_only:all"], execution_platform = "linux_arm64"),
    )

def _test_editor_only_set_overrides_editor_impl(env, target):
    _expect_package(env, target, "editor", Label(_FIXTURES + "/editor_only:all").package)
    _expect_hub(env, target, "runtime")

def _test_runtime_only_set_overrides_runtime(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_runtime_only_set_overrides_runtime_impl,
        config_settings = _settings([_FIXTURES + "/select:all"]),
    )

def _test_runtime_only_set_overrides_runtime_impl(env, target):
    _expect_hub(env, target, "editor")
    _expect_package(env, target, "runtime", Label(_FIXTURES + "/select:all").package)

def selection_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_registered_hub_supplies_both_roles,
            _test_complete_set_overrides_both_roles,
            _test_editor_only_set_overrides_editor,
            _test_runtime_only_set_overrides_runtime,
        ],
    )
