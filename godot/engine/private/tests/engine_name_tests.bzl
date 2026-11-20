"""--@autoload_rules_godot//godot:engine selects an engine by name; registration order decides within it.

Components that name an engine fill slots only in builds that name it, and the default
engine's components only in builds that name none. A named engine without an editor for an
execution platform moves its editor's actions to one that has one.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("//godot/engine/private/tests:engines.bzl", "ResolvedInfo")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

_FIXTURES = "//godot/engine/private/tests/fixtures"
_PLATFORMS = "//godot/engine/private/tests:"
_NAMED = _FIXTURES + "/named_engine:all"
_NAMED_MACOS = _FIXTURES + "/named_engine_macos:all"
_NAMED_FORWARD = _FIXTURES + "/named_forward:all"
_ENGINE = str(Label("//godot:engine"))

def _settings(engine, sets, target_platform = "linux_x86_64", execution_platforms = ["remote_linux"]):
    return {
        "//command_line_option:platforms": str(Label(_PLATFORMS + target_platform)),
        str(Label("//godot:variant")): "release",
        _ENGINE: engine,
    } | own_toolchains(sets, [_PLATFORMS + platform for platform in execution_platforms])

def _package(resolved):
    return Label(resolved.provenance.component).package if resolved else None

def _test_a_named_set_stays_out_of_builds_of_the_default_engine(name):
    analysis_test(
        name = name,
        target = _PLATFORMS + "probe",
        impl = _test_a_named_set_stays_out_of_builds_of_the_default_engine_impl,
        # The named set is registered ahead of the root module's prebuilt hub.
        config_settings = _settings("", [_NAMED]),
    )

def _test_a_named_set_stays_out_of_builds_of_the_default_engine_impl(env, target):
    for role in ["editor", "runtime"]:
        resolved = getattr(target[ResolvedInfo], role)
        env.expect.where(role = role).that_str(_package(resolved)).equals("toolchains")
        env.expect.where(role = role).that_str(resolved.provenance.engine).equals("")

def _test_naming_an_engine_takes_only_its_components(name):
    analysis_test(
        name = name,
        target = _PLATFORMS + "probe",
        impl = _test_naming_an_engine_takes_only_its_components_impl,
        config_settings = _settings("custom", [_NAMED]),
    )

def _test_naming_an_engine_takes_only_its_components_impl(env, target):
    for role in ["editor", "runtime"]:
        resolved = getattr(target[ResolvedInfo], role)
        env.expect.where(role = role).that_str(_package(resolved)).equals(Label(_NAMED).package)
        env.expect.where(role = role).that_str(resolved.provenance.engine).equals("custom")

def _test_a_slot_the_named_engine_lacks_takes_no_other_engine(name):
    analysis_test(
        name = name,
        target = _PLATFORMS + "probe",
        impl = _test_a_slot_the_named_engine_lacks_takes_no_other_engine_impl,
        # The prebuilt hub has a Linux arm64 runtime; the engine "custom" has none.
        config_settings = _settings("custom", [_NAMED], target_platform = "linux_arm64"),
    )

def _test_a_slot_the_named_engine_lacks_takes_no_other_engine_impl(env, target):
    env.expect.that_bool(target[ResolvedInfo].runtime == None).equals(True)
    env.expect.that_str(_package(target[ResolvedInfo].editor)).equals(Label(_NAMED).package)

def _test_editor_actions_move_to_an_execution_platform_with_the_named_editor(name):
    analysis_test(
        name = name,
        target = _PLATFORMS + "editor_probe",
        impl = _test_editor_actions_move_to_an_execution_platform_with_the_named_editor_impl,
        # The first execution platform has only the default engine's Linux editor.
        config_settings = _settings("custom", [_NAMED_MACOS], execution_platforms = ["remote_linux", "remote_macos"]),
    )

def _test_editor_actions_move_to_an_execution_platform_with_the_named_editor_impl(env, target):
    editor = target[ResolvedInfo].editor
    env.expect.that_str(_package(editor)).equals(Label(_NAMED_MACOS).package)
    env.expect.that_str(editor.provenance.platform).equals("macos")

def _test_the_default_engine_keeps_the_first_execution_platform(name):
    analysis_test(
        name = name,
        target = _PLATFORMS + "editor_probe",
        impl = _test_the_default_engine_keeps_the_first_execution_platform_impl,
        config_settings = _settings("", [_NAMED_MACOS], execution_platforms = ["remote_linux", "remote_macos"]),
    )

def _test_the_default_engine_keeps_the_first_execution_platform_impl(env, target):
    editor = target[ResolvedInfo].editor
    env.expect.that_str(_package(editor)).equals("toolchains")
    env.expect.that_str(editor.provenance.platform).equals("linux")

def _test_a_missing_slot_of_the_named_engine_fails_naming_the_flag(name):
    analysis_test(
        name = name,
        target = _PLATFORMS + "resolved_runtime",
        impl = _test_a_missing_slot_of_the_named_engine_fails_naming_the_flag_impl,
        config_settings = _settings("custom", [_NAMED], target_platform = "linux_arm64"),
        expect_failure = True,
    )

def _test_a_missing_slot_of_the_named_engine_fails_naming_the_flag_impl(env, target):
    env.expect.that_target(target).failures().contains_predicate(matching.contains(
        "no registered Godot runtime component of the selected engine matches this target platform",
    ))
    env.expect.that_target(target).failures().contains_predicate(matching.contains(
        "--@autoload_rules_godot//godot:engine",
    ))

def _test_a_forwarded_component_reports_the_forwarding_engine(name):
    analysis_test(
        name = name,
        target = _PLATFORMS + "probe",
        impl = _test_a_forwarded_component_reports_the_forwarding_engine_impl,
        config_settings = _settings("custom", [_NAMED_FORWARD]),
    )

def _test_a_forwarded_component_reports_the_forwarding_engine_impl(env, target):
    runtime = target[ResolvedInfo].runtime

    # The payload and its provenance come from the default engine's component.
    env.expect.that_str(_package(runtime)).equals(Label(_FIXTURES + ":all").package)
    env.expect.that_str(runtime.provenance.engine).equals("custom")

def engine_name_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_a_named_set_stays_out_of_builds_of_the_default_engine,
            _test_naming_an_engine_takes_only_its_components,
            _test_a_slot_the_named_engine_lacks_takes_no_other_engine,
            _test_editor_actions_move_to_an_execution_platform_with_the_named_editor,
            _test_the_default_engine_keeps_the_first_execution_platform,
            _test_a_missing_slot_of_the_named_engine_fails_naming_the_flag,
            _test_a_forwarded_component_reports_the_forwarding_engine,
        ],
    )
