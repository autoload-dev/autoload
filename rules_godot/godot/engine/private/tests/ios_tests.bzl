"""The iOS runtime component replays the Apple aspects through godot_source_library's deps."""

load("@rules_apple//apple:providers.bzl", "AppleResourceInfo")

# buildifier: disable=bzl-visibility
load("@rules_apple//apple/internal/aspects:swift_usage_aspect.bzl", "SwiftUsageInfo")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private/tests:engines.bzl", "ResolvedInfo")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

visibility("private")

def _test_ios_bridge_forwards_payload_providers(name):
    analysis_test(
        name = name,
        target = "//godot/engine/private/tests:probe",
        impl = _test_ios_bridge_forwards_payload_providers_impl,
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_arm64")),
            str(Label("//godot:variant")): "release",
        } | own_toolchains(["//godot/engine/private/tests/fixtures/source_built_ios:all"]),
        # iOS components apply Apple's aspects to their payload, which need macOS tools.
        attr_values = {"target_compatible_with": ["@platforms//os:macos"]},
    )

def _test_ios_bridge_forwards_payload_providers_impl(env, target):
    runtime = target[ResolvedInfo].runtime
    env.expect.that_bool(runtime != None, "the iOS simulator runtime must resolve").equals(True)
    if runtime:
        # The bridge forwards these from the payload; a hidden edge would drop them.
        env.expect.where(claim = "Swift usage must reach the payload").that_target(
            runtime.payload,
        ).has_provider(SwiftUsageInfo)
        env.expect.where(claim = "resources must reach the payload").that_target(
            runtime.payload,
        ).has_provider(AppleResourceInfo)

def ios_test_suite(name):
    test_suite(
        name = name,
        tests = [_test_ios_bridge_forwards_payload_providers],
    )
