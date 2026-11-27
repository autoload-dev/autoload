"""Component, toolchain-registration and provenance contracts of the engine primitives."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("@rules_testing//lib:unit_test.bzl", "unit_test")
load("//godot/engine:defs.bzl", "godot_editor_component", "godot_runtime_component")
load("//godot/engine/private:components.bzl", "runtime_slot_error")
load("//godot/engine/private:resolution.bzl", "engine_toolchain")
load("//godot/engine/private/tests:engines.bzl", "ResolvedInfo")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

visibility("private")

_RUNTIME = Label("//godot:runtime_toolchain_type")

def _required_impl(ctx):
    return [ResolvedInfo(editor = None, runtime = engine_toolchain(ctx, "runtime"))]

_required_runtime_probe = rule(
    doc = "Require a runtime candidate, as a packaging rule does.",
    implementation = _required_impl,
    toolchains = [config_common.toolchain_type(_RUNTIME, mandatory = False)],
)

_FIXTURES = "//godot/engine/private/tests/fixtures"
_PLATFORMS = "//godot/engine/private/tests:"
_PROBE = "//godot/engine/private/tests:probe"

# iOS components apply Apple's aspects to their payload, which need macOS tools.
_MACOS_ONLY = {"target_compatible_with": ["@platforms//os:macos"]}

# How components register and resolve is the subject, so the tests register their sets with
# --extra_toolchains rather than selecting a development engine by name.
def _settings(target_platform, variant = "release", sets = [_FIXTURES + ":all"], execution_platform = None, extra = {}):
    settings = {
        "//command_line_option:platforms": str(Label(_PLATFORMS + target_platform)),
        str(Label("//godot:variant")): variant,
    } | own_toolchains(sets, [_PLATFORMS + execution_platform] if execution_platform else None)
    return settings | extra

def _runtime(env, target):
    runtime = target[ResolvedInfo].runtime
    env.expect.that_bool(runtime != None, "a runtime must resolve").equals(True)
    return runtime

def _expect_runtime(env, target, component, platform, cpu, variant, environment = ""):
    runtime = _runtime(env, target)
    if not runtime:
        return None
    provenance = runtime.provenance
    env.expect.that_str(runtime.role).equals("runtime")
    env.expect.that_str(Label(provenance.component).name).equals(component)
    env.expect.that_str(provenance.platform).equals(platform)
    env.expect.that_str(provenance.cpu).equals(cpu)
    env.expect.that_str(provenance.variant).equals(variant)
    env.expect.that_str(provenance.environment).equals(environment)
    env.expect.that_str(provenance.version).equals("4.7.2")
    return runtime

def _expect_failures(env, target, messages):
    for message in messages:
        env.expect.that_target(target).failures().contains_predicate(matching.contains(message))

def _test_desktop_release_resolves_template_payload(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_desktop_release_resolves_template_payload_impl,
        config_settings = _settings("linux_x86_64"),
    )

def _test_desktop_release_resolves_template_payload_impl(env, target):
    runtime = _expect_runtime(env, target, "runtime_linux_x86_64_release", "linux", "x86_64", "release")
    if runtime:
        env.expect.that_str(runtime.provenance.kind).equals("prebuilt")
        env.expect.that_bool(
            runtime.runtime != None,
            "a template file payload yields GodotRuntimeInfo",
        ).equals(True)
        env.expect.that_str(runtime.runtime.executable.basename).equals("linux_x86_64_release.bin")

def _test_desktop_debug_resolves_debug_component(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_desktop_debug_resolves_debug_component_impl,
        config_settings = _settings("linux_x86_64", variant = "debug"),
    )

def _test_desktop_debug_resolves_debug_component_impl(env, target):
    _expect_runtime(env, target, "runtime_linux_x86_64_debug", "linux", "x86_64", "debug")

def _test_arm64_component_resolves_for_arm64(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_arm64_component_resolves_for_arm64_impl,
        config_settings = _settings("linux_arm64"),
    )

def _test_arm64_component_resolves_for_arm64_impl(env, target):
    _expect_runtime(env, target, "runtime_linux_arm64_release", "linux", "arm64", "release")

def _test_ios_device_resolves_device_component(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_ios_device_resolves_device_component_impl,
        config_settings = _settings("ios_arm64"),
        attr_values = _MACOS_ONLY,
    )

def _test_ios_device_resolves_device_component_impl(env, target):
    _expect_runtime(env, target, "runtime_ios_arm64_device_release", "ios", "arm64", "release", "device")

def _test_ios_simulator_resolves_simulator_component(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_ios_simulator_resolves_simulator_component_impl,
        config_settings = _settings("ios_sim_arm64"),
        attr_values = _MACOS_ONLY,
    )

def _test_ios_simulator_resolves_simulator_component_impl(env, target):
    _expect_runtime(env, target, "runtime_ios_arm64_simulator_release", "ios", "arm64", "release", "simulator")

def _test_payload_select_follows_configuration(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_payload_select_follows_configuration_impl,
        config_settings = _settings(
            "linux_x86_64",
            sets = [_FIXTURES + "/select:all"],
            extra = {"//command_line_option:compilation_mode": "opt"},
        ),
    )

def _test_payload_select_follows_configuration_impl(env, target):
    runtime = _expect_runtime(env, target, "runtime_linux_x86_64_release", "linux", "x86_64", "release")
    if runtime:
        env.expect.that_str(runtime.runtime.executable.basename).equals("optimized.bin")

def _test_forwarding_component_forwards_hub_component(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_forwarding_component_forwards_hub_component_impl,
        config_settings = _settings("linux_x86_64", sets = [_FIXTURES + "/forward:all"]),
    )

def _test_forwarding_component_forwards_hub_component_impl(env, target):
    # The outer component names a hub component; payload and provenance are forwarded.
    runtime = _expect_runtime(env, target, "runtime_linux_x86_64_release", "linux", "x86_64", "release")
    if runtime:
        env.expect.that_str(str(Label(runtime.provenance.component))).equals(
            str(Label(_FIXTURES + ":runtime_linux_x86_64_release")),
        )

def _test_editor_resolves_on_execution_platform(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_editor_resolves_on_execution_platform_impl,
        config_settings = _settings("linux_x86_64", execution_platform = "linux_arm64"),
    )

def _test_editor_resolves_on_execution_platform_impl(env, target):
    editor = target[ResolvedInfo].editor
    env.expect.that_bool(editor != None, "an editor must resolve on the execution platform").equals(True)
    if editor:
        env.expect.that_str(editor.role).equals("editor")
        env.expect.that_str(Label(editor.provenance.component).name).equals("editor_linux_arm64")
        env.expect.that_bool(
            editor.editor.executable != None,
            "the editor payload is executable",
        ).equals(True)

def _test_required_runtime_without_candidate_fails(name):
    _required_runtime_probe(
        name = name + "_probe",
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = name + "_probe",
        impl = _test_required_runtime_without_candidate_fails_impl,
        expect_failure = True,
        config_settings = _settings("linux_riscv64"),
    )

def _test_required_runtime_without_candidate_fails_impl(env, target):
    _expect_failures(env, target, ["no registered Godot runtime component of the selected engine matches this target platform"])

# Mobile components reject payloads without their payload provider, JavaInfo or CcInfo.
def _test_android_payload_without_java_info_fails(name):
    analysis_test(
        name = name,
        target = _FIXTURES + "/invalid:runtime_android_arm64_release",
        impl = _test_android_payload_without_java_info_fails_impl,
        expect_failure = True,
    )

def _test_android_payload_without_java_info_fails_impl(env, target):
    _expect_failures(env, target, ["runtime payload", "has no JavaInfo"])

def _test_ios_payload_without_cc_info_fails(name):
    analysis_test(
        name = name,
        target = _FIXTURES + "/invalid:runtime_ios_arm64_device_release",
        impl = _test_ios_payload_without_cc_info_fails_impl,
        expect_failure = True,
    )

def _test_ios_payload_without_cc_info_fails_impl(env, target):
    _expect_failures(env, target, ["runtime payload", "has no CcInfo"])

# A payload's own slot facts, or a forwarded component's slot, must match the declaration.
_CONTRADICTION = "is for cpu \"arm64\", but the component declares \"x86_64\""

def _test_contradicting_payload_slot_fails(name):
    analysis_test(
        name = name,
        target = _FIXTURES + "/invalid:contradicting_payload",
        impl = _test_contradicting_slot_fails_impl,
        expect_failure = True,
    )

def _test_contradicting_forward_slot_fails(name):
    analysis_test(
        name = name,
        target = _FIXTURES + "/invalid:contradicting_forward",
        impl = _test_contradicting_slot_fails_impl,
        expect_failure = True,
    )

def _test_contradicting_slot_fails_impl(env, target):
    _expect_failures(env, target, [_CONTRADICTION])

# A slot's payload must be what its role needs: an executable editor, or a payload or
# forwarded component of the same role.
def _payload(name):
    native.genrule(
        name = name,
        outs = [name + ".bin"],
        cmd = "echo 'Analysis-only stand-in' > $@",
        tags = ["manual"],
    )
    return ":" + name

def _editor(name, editor, **kwargs):
    godot_editor_component(
        name = name,
        cpu = "arm64",
        editor = editor,
        platform = "linux",
        version = "4.7.2",
        **kwargs
    )

def _runtime_component(name, runtime):
    godot_runtime_component(
        name = name,
        cpu = "x86_64",
        platform = "linux",
        runtime = runtime,
        tags = ["manual"],
        variant = "release",
        version = "4.7.2",
    )

def _component_failure_test(name, target, message):
    analysis_test(
        name = name,
        target = target,
        impl = _component_fails_with_message,
        attrs = {"message": attr.string()},
        attr_values = {"message": message},
        expect_failure = True,
    )

def _component_fails_with_message(env, target):
    _expect_failures(env, target, [env.ctx.attr.message])

# A filegroup of one file runs that file, so the stand-in holds two.
def _test_non_executable_editor_fails(name):
    native.filegroup(
        name = name + "_files",
        srcs = [_payload(name + "_first"), _payload(name + "_second")],
        tags = ["manual"],
    )
    _editor(name + "_editor", ":" + name + "_files", tags = ["manual"])
    _component_failure_test(name, name + "_editor", "must be an executable target")

def _test_runtime_component_as_editor_fails(name):
    _runtime_component(name + "_runtime", _payload(name + "_payload"))
    _editor(name + "_editor", ":" + name + "_runtime", tags = ["manual"])
    _component_failure_test(name, name + "_editor", "is a runtime component, not a editor component")

def _test_editor_component_as_runtime_fails(name):
    _editor(name + "_editor", _FIXTURES + ":editor_stand_in", tags = ["manual"])
    _runtime_component(name + "_runtime", ":" + name + "_editor")
    _component_failure_test(name, name + "_runtime", "is a editor component, not a runtime component")

def _test_editor_component_tags_reach_toolchain(name):
    _editor(name + "_editor", _FIXTURES + ":editor_stand_in", tags = ["manual", "component_tag"])
    analysis_test(
        name = name,
        target = name + "_editor.toolchain",
        impl = _editor_component_tags_reach_toolchain,
    )

def _editor_component_tags_reach_toolchain(env, target):
    env.expect.that_target(target).tags().contains_at_least(["manual", "component_tag"])

def _runtime_slot_errors(platform, environment):
    errors = []
    runtime_slot_error("fixture", platform, environment, _fail = errors.append)
    return errors

def _test_ios_runtime_without_environment_fails(name):
    unit_test(name = name, impl = _ios_runtime_without_environment_fails)

def _ios_runtime_without_environment_fails(env):
    for environment in ["", "watch"]:
        env.expect.where(environment = environment).that_collection(
            _runtime_slot_errors("ios", environment),
        ).contains_exactly(["fixture: iOS runtimes require environment = device or simulator"])
    for environment in ["device", "simulator"]:
        env.expect.where(environment = environment).that_collection(
            _runtime_slot_errors("ios", environment),
        ).contains_exactly([])

def _test_environment_outside_ios_fails(name):
    unit_test(name = name, impl = _environment_outside_ios_fails)

def _environment_outside_ios_fails(env):
    env.expect.that_collection(_runtime_slot_errors("android", "device")).contains_exactly([
        "fixture: environment is only valid for iOS runtimes",
    ])
    env.expect.that_collection(_runtime_slot_errors("android", "")).contains_exactly([])

def components_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_desktop_release_resolves_template_payload,
            _test_desktop_debug_resolves_debug_component,
            _test_arm64_component_resolves_for_arm64,
            _test_ios_device_resolves_device_component,
            _test_ios_simulator_resolves_simulator_component,
            _test_payload_select_follows_configuration,
            _test_forwarding_component_forwards_hub_component,
            _test_editor_resolves_on_execution_platform,
            _test_required_runtime_without_candidate_fails,
            _test_android_payload_without_java_info_fails,
            _test_ios_payload_without_cc_info_fails,
            _test_contradicting_payload_slot_fails,
            _test_contradicting_forward_slot_fails,
            _test_non_executable_editor_fails,
            _test_runtime_component_as_editor_fails,
            _test_editor_component_as_runtime_fails,
            _test_editor_component_tags_reach_toolchain,
            _test_ios_runtime_without_environment_fails,
            _test_environment_outside_ios_fails,
        ],
    )
