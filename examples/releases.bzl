"""
The release builds of the repository's applications, declared beside each one's `godot_app`.

`android_release` and `ios_release` build an application and its debug symbols as
`godot_configured_app` does, under the settings of the `.bazelrc` configurations
`android-release`, `multi_abi` and `aab`, and of `ios-release`. The Android and iOS lanes
build them in the same Bazel invocation and configuration as everything else.
"""

# The ruleset's configured applications, which it does not support as API.
# buildifier: disable=bzl-visibility
load(
    "@autoload_rules_godot//godot/private:configured_app.bzl",
    "ANDROID_RELEASE",
    "APPLE_RELEASE",
    "godot_configured_app",
)

def android_release(name, app = ":app", **kwargs):
    """
    The multi-ABI release App Bundle of an application, with its debug symbols.

    Args:
        name: the name of the App Bundle; its debug symbols are `<name>.debug_symbols`.
        app: the `godot_app`.
        **kwargs: common attributes such as `visibility`; `tags` add to `manual`.
    """
    godot_configured_app(
        name = name,
        app = app,
        android_format = "aab",
        platform = Label("//examples:android_distribution"),
        tags = ["manual"] + kwargs.pop("tags", []),
        **(ANDROID_RELEASE | kwargs)
    )

def ios_release(name, app = ":app", **kwargs):
    """
    The release iOS Simulator application of the official templates, with its dSYMs.

    Args:
        name: the name of the application; its debug symbols are `<name>.debug_symbols`.
        app: the `godot_app`.
        **kwargs: common attributes such as `visibility`; `tags` add to `manual`.
    """
    godot_configured_app(
        name = name,
        app = app,
        platform = Label("@autoload_rules_godot//godot/platforms:ios_sim_x86_64"),
        tags = ["manual"] + kwargs.pop("tags", []),
        **(APPLE_RELEASE | kwargs)
    )
