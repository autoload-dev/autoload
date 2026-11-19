"""
Which signing inputs of a godot_app reach the signing actions of its mobile backends.

An Android APK is signed with the declared debug keystore instead of rules_android's. An iOS
application reads its declared provisioning profile and entitlements file when it prepares
its signing entitlements.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:app.bzl", "godot_app")
load(":action_graph.bzl", "reached", "reached_actions", "reads")
load(":android_settings.bzl", "ANDROID", "ANDROID_SDK")

_PACK = "//godot/platforms/private/tests/fixtures/mobile_app_with_platform_libraries:pack"
_PACKAGE = "godot/platforms/private/tests/"

# Apple applications need Xcode, which only a macOS host has.
_IOS = {"//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_x86_64"))}
_MACOS_HOST = {"size": "small", "target_compatible_with": ["@platforms//os:macos"]}

def _signing_input(name, extension):
    """Declare an analysis-only stand-in for a signing file and return its short path."""
    native.genrule(
        name = name,
        outs = [name + extension],
        cmd = "echo 'Analysis-only stand-in' > $@",
        tags = ["manual"],
    )
    return _PACKAGE + name + extension

def _expect_read_by(env, target, mnemonic, path):
    actions = [entry.action for entry in reached(target) if entry.action.mnemonic == mnemonic]
    env.expect.where(mnemonic = mnemonic).that_collection(actions).has_size(1)
    for action in actions:
        env.expect.where(mnemonic = mnemonic, path = path).that_bool(
            reads(action, path),
            expr = "the action reads the declared signing input",
        ).equals(True)

def _android_debug_key_signs_apk(env, target):
    _expect_read_by(env, target, "ApkSignerTool", env.ctx.attr.path)
    env.expect.where(path = "tools/android/bazel_debug.keystore").that_bool(
        any([reads(entry.action, "tools/android/bazel_debug.keystore") for entry in reached(target)]),
        expr = "no action reads rules_android's default debug keystore",
    ).equals(False)

def _test_android_debug_key_signs_apk(name):
    path = _signing_input(name + "_key", ".keystore")
    godot_app(
        name = name + "_app",
        android_debug_key = ":" + name + "_key",
        application_id = "org.example.signinginputs",
        pack = _PACK,
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = name + "_app",
        impl = _android_debug_key_signs_apk,
        attrs = {"path": attr.string()},
        config_settings = ANDROID,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = ANDROID_SDK | {"path": path},
    )

def _ios_signing_test(name, impl, extension, attribute):
    path = _signing_input(name + "_input", extension)
    godot_app(
        name = name + "_app",
        application_id = "org.example.signinginputs",
        pack = _PACK,
        tags = ["manual"],
        **{attribute: ":" + name + "_input"}
    )
    analysis_test(
        name = name,
        target = name + "_app",
        impl = impl,
        attrs = {"path": attr.string()},
        config_settings = _IOS,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = _MACOS_HOST | {"path": path},
    )

def _ios_provisioning_profile_reaches_signing(env, target):
    _expect_read_by(env, target, "ExtractFromProvisioningProfile", env.ctx.attr.path)

def _test_ios_provisioning_profile_reaches_signing(name):
    _ios_signing_test(
        name,
        _ios_provisioning_profile_reaches_signing,
        ".mobileprovision",
        "ios_provisioning_profile",
    )

def _ios_entitlements_reach_signing(env, target):
    _expect_read_by(env, target, "ProcessEntitlementsFiles", env.ctx.attr.path)

def _test_ios_entitlements_reach_signing(name):
    _ios_signing_test(name, _ios_entitlements_reach_signing, ".entitlements", "ios_entitlements")

def signing_inputs_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_android_debug_key_signs_apk,
            _test_ios_provisioning_profile_reaches_signing,
            _test_ios_entitlements_reach_signing,
        ],
    )
