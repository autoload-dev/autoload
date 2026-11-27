"""
The release builds of the repository's applications, declared beside each one's `godot_app`.

`android_release` and `ios_release` build an application and its debug symbols as
`godot_configured_app` does, under the settings of the `.bazelrc` configurations
`android-release`, `multi_abi` and `aab`, and of `ios-release`. Each also declares
`<name>.build_test`, which builds both, tagged with its mobile operating system, `android` or `ios`: CI's host jobs run it in the
same Bazel invocation and configuration as everything else (shared.bazelrc).
"""

load("@bazel_skylib//rules:build_test.bzl", "build_test")
load(":configured_app.bzl", "ANDROID_RELEASE", "APPLE_RELEASE", "godot_configured_app")

def _release_test(name, os_tag, target_compatible_with = []):
    """Build a release and its debug symbols as a test tagged with its mobile operating system, which starts Godot."""
    build_test(
        name = name + ".build_test",
        size = "small",
        tags = [os_tag, "godot_process"],
        target_compatible_with = target_compatible_with,
        targets = [name, name + ".debug_symbols"],
    )

def android_release(name, app = ":app", **kwargs):
    """
    The multi-ABI release App Bundle of an application, with its debug symbols.

    Args:
        name: the name of the App Bundle; its debug symbols are `<name>.debug_symbols`, the
            test that builds both `<name>.build_test`.
        app: the `godot_app`.
        **kwargs: common attributes such as `visibility`; `tags` add to `manual`.
    """
    godot_configured_app(
        name = name,
        app = app,
        debug_symbols = app + ".debug_symbols",
        android_format = "aab",
        platform = Label("//examples:android_distribution"),
        tags = ["manual"] + kwargs.pop("tags", []),
        **(ANDROID_RELEASE | kwargs)
    )
    _release_test(name, "android")

def ios_release(name, app = ":app", **kwargs):
    """
    The release iOS Simulator application of the official templates, with its dSYMs.

    Args:
        name: the name of the application; its debug symbols are `<name>.debug_symbols`,
            the test that builds both `<name>.build_test`.
        app: the `godot_app`.
        **kwargs: common attributes such as `visibility`; `tags` add to `manual`.
    """
    godot_configured_app(
        name = name,
        app = app,
        debug_symbols = app + ".debug_symbols",
        platform = Label("@autoload_rules_godot//godot/platforms:ios_sim_x86_64"),
        tags = ["manual"] + kwargs.pop("tags", []),
        **(APPLE_RELEASE | kwargs)
    )
    _release_test(name, "ios", ["@platforms//os:macos"])
