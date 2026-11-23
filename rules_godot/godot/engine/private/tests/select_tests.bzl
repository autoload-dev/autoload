"""A payload select() between prepared same-slot components resolves the selected one."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private/tests:engines.bzl", "ResolvedInfo")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

_FIXTURES = "//godot/engine/private/tests/fixtures"

# The unselected branch names @godot_unconfigured_fixture, which fails if configured.
def _test_component_select_forwards_selected_component(name):
    analysis_test(
        name = name,
        target = "//godot/engine/private/tests:probe",
        impl = _test_component_select_forwards_selected_component_impl,
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/engine/private/tests:linux_x86_64")),
            "//command_line_option:compilation_mode": "opt",
            str(Label("//godot:variant")): "release",
        } | own_toolchains([_FIXTURES + "/select_recipe:all"]),
    )

def _test_component_select_forwards_selected_component_impl(env, target):
    runtime = target[ResolvedInfo].runtime
    env.expect.that_bool(runtime != None, "a runtime must resolve").equals(True)
    if runtime:
        # The selected component's payload and provenance are forwarded.
        env.expect.that_str(str(Label(runtime.provenance.component))).equals(
            str(Label(_FIXTURES + ":runtime_linux_x86_64_release")),
        )
        env.expect.that_str(runtime.runtime.executable.basename).equals("linux_x86_64_release.bin")

def select_test_suite(name):
    test_suite(
        name = name,
        tests = [_test_component_select_forwards_selected_component],
    )
