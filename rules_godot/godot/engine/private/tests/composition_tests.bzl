"""Mixed registration: a registration set ahead of a full one replaces only its own slots.

The other slots stay unchanged. A requested slot that no registered set fills is covered by
_test_required_runtime_without_candidate_fails in components_tests.bzl.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private/tests:engines.bzl", "ResolvedInfo")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

visibility("private")

_FIXTURES = "//godot/engine/private/tests/fixtures"
_PLATFORMS = "//godot/engine/private/tests:"
_PROBE = "//godot/engine/private/tests:probe"

# iOS components apply Apple's aspects to their payload, which need macOS tools.
_MACOS_ONLY = {"target_compatible_with": ["@platforms//os:macos"]}

def _mixed(target_platform):
    # --extra_toolchains gives its last entry priority, which is the subject: the overriding
    # registration set goes ahead.
    return {
        "//command_line_option:platforms": str(Label(_PLATFORMS + target_platform)),
        str(Label("//godot:variant")): "release",
    } | own_toolchains([_FIXTURES + ":all", _FIXTURES + "/simulator_override:all"])

def _expect_component(env, target, package, name):
    runtime = target[ResolvedInfo].runtime
    env.expect.that_bool(runtime != None, "a runtime must resolve").equals(True)
    if runtime:
        env.expect.that_str(str(Label(runtime.provenance.component))).equals(
            str(Label(package + ":" + name)),
        )

def _test_mixed_registration_replaces_simulator_slot(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_mixed_registration_replaces_simulator_slot_impl,
        config_settings = _mixed("ios_sim_arm64"),
        attr_values = _MACOS_ONLY,
    )

def _test_mixed_registration_replaces_simulator_slot_impl(env, target):
    _expect_component(env, target, _FIXTURES + "/simulator_override", "runtime_ios_arm64_simulator_release")

def _test_mixed_registration_keeps_device_slot(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_mixed_registration_keeps_device_slot_impl,
        config_settings = _mixed("ios_arm64"),
        attr_values = _MACOS_ONLY,
    )

def _test_mixed_registration_keeps_device_slot_impl(env, target):
    _expect_component(env, target, _FIXTURES, "runtime_ios_arm64_device_release")

def _test_mixed_registration_keeps_desktop_slot(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_mixed_registration_keeps_desktop_slot_impl,
        config_settings = _mixed("linux_x86_64"),
    )

def _test_mixed_registration_keeps_desktop_slot_impl(env, target):
    _expect_component(env, target, _FIXTURES, "runtime_linux_x86_64_release")

def composition_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_mixed_registration_replaces_simulator_slot,
            _test_mixed_registration_keeps_device_slot,
            _test_mixed_registration_keeps_desktop_slot,
        ],
    )
