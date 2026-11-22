"""Application context defaults and Godot mirror values are shared by export and packaging."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/private:export_options.bzl", "resolve_export_options")
load("//godot/private/config:application.bzl", "application_context", "application_pack")
load("//godot/private/engine:profiles.bzl", "engine_profile")
load(":failures.bzl", "failure_test")

def _test_application_context_derives_export_option_defaults(env):
    profile = engine_profile("4.7.2")
    android = resolve_export_options({}, struct(cpus = ["arm64"], operating_system = "android", application_context = {
        "application_id": "org.example.game",
        "android_min_sdk_version": 0,
        "android_target_sdk_version": 0,
    }), profile, "4.7.2").pack_options
    env.expect.that_str(android["package/unique_name"]).equals('\"org.example.game\"')
    env.expect.that_str(android["gradle_build/min_sdk"]).equals('\"24\"')
    env.expect.that_str(android["gradle_build/target_sdk"]).equals('\"36\"')
    ios = resolve_export_options({}, struct(cpus = ["arm64"], operating_system = "ios", application_context = {
        "application_id": "org.example.game",
        "ios_minimum_os_version": "15.0",
        "ios_families": ["iphone", "ipad"],
    }), profile, "4.7.2").pack_options
    env.expect.that_str(ios["application/targeted_device_family"]).equals("2")
    env.expect.that_str(ios["application/min_ios_version"]).equals('\"15.0\"')
    unchanged = resolve_export_options({"application/bundle_identifier": '\"org.example.game\"'}, struct(cpus = ["arm64"], operating_system = "macos", application_context = {"application_id": "org.example.game"}), profile, "4.7.2").pack_options
    env.expect.that_dict(unchanged).contains_exactly({"application/bundle_identifier": '\"org.example.game\"'})
    macos = resolve_export_options({}, struct(cpus = ["arm64"], operating_system = "macos", application_context = {
        "application_id": "org.example.game",
        "macos_minimum_os_version": "12.0",
    }), profile, "4.7.2").pack_options
    env.expect.that_str(macos["application/min_macos_version_arm64"]).equals('\"12.0\"')
    env.expect.that_str(macos["application/min_macos_version_x86_64"]).equals('\"12.0\"')
    for families, expected in [(["iphone"], "0"), (["ipad"], "1"), (["ipad", "iphone"], "2")]:
        context = struct(operating_system = "ios", cpus = ["x86_64"], application_context = {"ios_families": families, "ios_minimum_os_version": "16.1"})
        result = resolve_export_options({"application/min_ios_version": '"16.1"'}, context, profile, "4.7.2")
        expect = env.expect.where(ios_families = families)
        expect.that_str(result.pack_options["application/targeted_device_family"]).equals(expected)
        expect.that_str(result.preset_options["architectures/arm64"]).equals("false")
    empty = struct(operating_system = "macos", cpus = ["arm64"], application_context = {"application_id": ""})
    env.expect.that_dict(resolve_export_options({}, empty, profile, "4.7.2").pack_options).contains_exactly({})
    authored = {"application/bundle_identifier": '"org.example.standalone"'}
    env.expect.that_dict(resolve_export_options(authored, empty, profile, "4.7.2").pack_options).contains_exactly(authored)
    explicit = struct(operating_system = "android", cpus = ["arm64", "x86_64"], application_context = {"android_min_sdk_version": 25, "android_target_sdk_version": 37})
    result = resolve_export_options({}, explicit, profile, "4.7.2")
    env.expect.that_dict(result.pack_options).contains_exactly({"gradle_build/min_sdk": '"25"', "gradle_build/target_sdk": '"37"'})
    env.expect.that_str(result.preset_options["architectures/x86_64"]).equals("true")

def _input_fixture_impl(ctx):
    resolve_export_options(json.decode(ctx.attr.authored), struct(operating_system = ctx.attr.operating_system, cpus = ["arm64"], application_context = json.decode(ctx.attr.application_context)), engine_profile("4.7.2"), "4.7.2")
    return []

_input_fixture = rule(
    implementation = _input_fixture_impl,
    attrs = {"operating_system": attr.string(default = "android"), "application_context": attr.string(default = "{}"), "authored": attr.string(default = "{}")},
)

# Transition errors abort analysis before AnalysisFailureInfo is available.
# Invoke the exact transition implementation in rule analysis so assertions can
# inspect its diagnostics; the manual application_pack fixtures retain the real edge.
def _transition_input_impl(ctx):
    application_context({str(Label("//godot/private/config:operating_system")): ctx.attr.operating_system}, ctx.attr)
    return []

_transition_input = rule(
    implementation = _transition_input_impl,
    attrs = {
        "operating_system": attr.string(),
        "application_id": attr.string(default = "org.example.boundary"),
        "android_min_sdk_version": attr.int(),
        "android_target_sdk_version": attr.int(),
        "macos_minimum_os_version": attr.string(default = "11.0"),
        "ios_minimum_os_version": attr.string(default = "15.0"),
        "ios_families": attr.string_list(default = ["iphone", "ipad"]),
    },
)

def _test_android_target_sdk_below_minimum_fails(name):
    targets = []
    for case, minimum, target_sdk in [("sdk_floor", 23, 36), ("sdk_order", 30, 29), ("sdk_fallback_order", 40, 0)]:
        _input_fixture(name = name + "_" + case, application_context = json.encode({"android_min_sdk_version": minimum, "android_target_sdk_version": target_sdk}), tags = ["manual"])
        targets.append(":" + name + "_" + case)
    failure_test(name, "Android target SDK must be >= minimum SDK", targets)

def _test_authored_equal_bazel_owned_value_fails(name):
    targets = []
    for case, key, value in [("forbidden_equal_cpu", "architectures/arm64-v8a", "true"), ("forbidden_equal_sdk", "gradle_build/min_sdk", '"24"')]:
        _input_fixture(name = name + "_" + case, authored = json.encode({key: value}), tags = ["manual"])
        targets.append(":" + name + "_" + case)
    failure_test(name, "is bazel-owned", targets)

def _test_unequal_ios_mirror_fails(name):
    _input_fixture(
        name = name + "_subject",
        operating_system = "ios",
        authored = json.encode({"application/min_ios_version": '"14.0"'}),
        application_context = json.encode({"ios_families": ["iphone"], "ios_minimum_os_version": "15.0"}),
        tags = ["manual"],
    )
    failure_test(name, "conflicts with authoritative godot_app value", [":" + name + "_subject"])

def _application_input_failure_test(name, operating_system, message, cases):
    """Declare manual application_pack fixtures and a failure test of their transition inputs."""
    targets = []
    for case, attrs in cases.items():
        application_pack(name = name + "_" + case, application_id = "org.example.boundary", deps = [":empty_pack"], tags = ["manual"], **attrs)
        _transition_input(name = name + "_" + case + "_input", operating_system = operating_system, tags = ["manual"], **attrs)
        targets.append(":" + name + "_" + case + "_input")
    failure_test(name, message, targets)

def _test_negative_android_sdk_fails(name):
    _application_input_failure_test(name, "android", "Android SDK values must be zero or positive", {
        "negative_sdk": {"android_min_sdk_version": -1},
    })

def _test_invalid_ios_families_fail(name):
    _application_input_failure_test(name, "ios", "ios_families must be a nonempty unique subset of iphone, ipad", {
        "empty_families": {"ios_families": []},
        "duplicate_families": {"ios_families": ["iphone", "iphone"]},
        "unknown_family": {"ios_families": ["watch"]},
    })

def _test_invalid_ios_minimum_os_version_fails(name):
    _application_input_failure_test(name, "ios", "ios_minimum_os_version must be a dotted numeric version", {
        "invalid_minimum_os": {"ios_minimum_os_version": "15.x"},
    })

def _test_invalid_macos_minimum_os_version_fails(name):
    _application_input_failure_test(name, "macos", "macos_minimum_os_version must be a dotted numeric version", {
        "invalid_macos_minimum_os": {"macos_minimum_os_version": "11.a"},
    })

def _application_pack_without_android_debug_runtime_impl(env, target):
    env.expect.that_bool(GodotPackInfo in target).equals(True)

# The registered prebuilt hub has no Android debug runtime: the pack must not resolve
# one; only the application's Android split does.
def _test_application_pack_without_android_debug_runtime_analyzes(name):
    analysis_test(
        name = name,
        target = ":application_context",
        impl = _application_pack_without_android_debug_runtime_impl,
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/platforms:android_arm64")),
            str(Label("//godot:variant")): "debug",
        },
    )

def application_options_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_android_target_sdk_below_minimum_fails,
            _test_authored_equal_bazel_owned_value_fails,
            _test_unequal_ios_mirror_fails,
            _test_negative_android_sdk_fails,
            _test_invalid_ios_families_fail,
            _test_invalid_ios_minimum_os_version_fails,
            _test_invalid_macos_minimum_os_version_fails,
            _test_application_pack_without_android_debug_runtime_analyzes,
        ],
        basic_tests = [
            _test_application_context_derives_export_option_defaults,
        ],
    )
