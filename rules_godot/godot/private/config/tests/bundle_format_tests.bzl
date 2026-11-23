"""Observe the iOS bundle format each build purpose selects."""

load("@rules_apple//apple:providers.bzl", "AppleBundleInfo")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

def _bundle_format_test(name, platform, compilation_mode, extension):
    # Its device and simulator runtimes come from the platform_slice_engines registration set.
    analysis_test(
        name = name,
        target = ":bundle_format_app",
        impl = _bundle_format,
        attrs = {"extension": attr.string(mandatory = True)},
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/platforms:" + platform)),
            "//command_line_option:compilation_mode": compilation_mode,
        } | own_toolchains(["//godot/private/config/tests/platform_slice_engines:all"]),
        attr_values = {
            "extension": extension,
            "size": "small",
            "target_compatible_with": ["@platforms//os:macos"],
        },
    )

def _bundle_format(env, target):
    env.expect.that_str(target[AppleBundleInfo].archive.extension).equals(env.ctx.attr.extension)

def _test_optimized_simulator_app_stays_directory(name):
    """A Simulator app is never distributed, so even an optimized one stays a directory."""
    _bundle_format_test(name, "ios_sim_arm64", "opt", "app")

def _test_unoptimized_device_app_stays_directory(name):
    """An unoptimized device app stays a directory."""
    _bundle_format_test(name, "ios_arm64", "fastbuild", "app")

def _test_optimized_device_app_is_distribution_archive(name):
    """An optimized device app is the archive for distribution."""
    _bundle_format_test(name, "ios_arm64", "opt", "ipa")

def bundle_format_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_optimized_simulator_app_stays_directory,
            _test_unoptimized_device_app_stays_directory,
            _test_optimized_device_app_is_distribution_archive,
        ],
    )
