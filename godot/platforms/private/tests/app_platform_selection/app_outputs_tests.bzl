"""
What an Android application and its debug symbols companion deliver, and that the
editor variant's backend runs from sources on an export platform.

An App Bundle application delivers only its unsigned bundle and no intermediate APK, and the
`<name>.debug_symbols` companion delivers one archive named after the application, for an
APK on one CPU and for an App Bundle on both.
"""

load("@platforms//host:constraints.bzl", "HOST_CONSTRAINTS")
load("@rules_android//providers:providers.bzl", "AndroidBundleInfo", "ApkInfo")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

_APP = "//godot/platforms/private/tests/app_platform_selection/fixtures/app_selecting_platform_libraries:app"
_BOTH_CPUS = "//godot/platforms/private/tests/app_platform_selection/fixtures/export_platforms_with_both_cpus:"

_FORMAT = str(Label("//godot:android_format"))
_VARIANT = str(Label("//godot:variant"))

_FIXTURE = "//godot/platforms/private/tests/app_platform_selection/fixtures/project_with_desktop_apps:"

# The export platform of this host, whose editor the host can resolve.
_HOST_EXPORT_PLATFORM = "%s_%s" % (
    "linux" if "@platforms//os:linux" in HOST_CONSTRAINTS else "macos",
    "arm64" if "@platforms//cpu:aarch64" in HOST_CONSTRAINTS else "x86_64",
)

def _on(platform, variant):
    return {"//command_line_option:platforms": str(Label(platform)), _VARIANT: variant}

def _test_editor_variant_runs_from_sources_on_an_export_platform(name):
    analysis_test(
        name = name,
        target = _FIXTURE + "app",
        impl = _editor_variant_runs_from_sources_on_an_export_platform,
        config_settings = _on("//godot/platforms:" + _HOST_EXPORT_PLATFORM, "editor"),
        attr_values = {"size": "small"},
    )

def _editor_variant_runs_from_sources_on_an_export_platform(env, target):
    # The source application's launcher, not the bundle of the export platform.
    env.expect.that_collection(
        [file.basename for file in target[DefaultInfo].files.to_list()],
    ).contains_exactly(["app.editor.run"])

_ANDROID_TOOLCHAINS = own_toolchains(["@androidsdk//:all", "@android_toolchains//:all"])

# Android applications need an installed Android SDK; without one the tests are skipped.
_ANDROID_SDK = {
    "size": "small",
    "target_compatible_with": [Label("//godot/platforms/private/tests:requires_android_sdk")],
}

def _android(platform, android_format):
    return {
        "//command_line_option:platforms": str(Label(platform)),
        _FORMAT: android_format,
    } | _ANDROID_TOOLCHAINS

def _test_app_bundle_delivers_only_unsigned_bundle(name):
    analysis_test(
        name = name,
        target = _APP,
        impl = _app_bundle_delivers_only_unsigned_bundle,
        config_settings = _android(_BOTH_CPUS + "common_android", "aab"),
        attr_values = _ANDROID_SDK,
    )

def _app_bundle_delivers_only_unsigned_bundle(env, target):
    env.expect.that_target(target).has_provider(AndroidBundleInfo, "AndroidBundleInfo")
    env.expect.that_bool(ApkInfo in target, expr = "ApkInfo in target").equals(False)
    env.expect.that_collection(
        target[DefaultInfo].files.to_list(),
        expr = "DefaultInfo.files",
    ).contains_exactly([target[AndroidBundleInfo].unsigned_aab])

def _expect_debug_symbols_archive(env, target):
    env.expect.that_collection(
        [file.basename for file in target[DefaultInfo].files.to_list()],
        expr = "debug symbols file names",
    ).contains_exactly(["app_debug_symbols.zip"])

def _test_apk_debug_symbols_archive_is_named_after_app(name):
    analysis_test(
        name = name,
        target = _APP + ".debug_symbols",
        impl = _expect_debug_symbols_archive,
        config_settings = _android("//godot/platforms:android_arm64", "apk"),
        attr_values = _ANDROID_SDK,
    )

def _test_app_bundle_debug_symbols_archive_is_named_after_app(name):
    analysis_test(
        name = name,
        target = _APP + ".debug_symbols",
        impl = _expect_debug_symbols_archive,
        config_settings = _android(_BOTH_CPUS + "common_android", "aab"),
        attr_values = _ANDROID_SDK,
    )

def app_outputs_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_app_bundle_delivers_only_unsigned_bundle,
            _test_apk_debug_symbols_archive_is_named_after_app,
            _test_app_bundle_debug_symbols_archive_is_named_after_app,
            _test_editor_variant_runs_from_sources_on_an_export_platform,
        ],
    )
