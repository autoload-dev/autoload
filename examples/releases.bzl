"""
The release builds of the repository's applications, declared beside each one's `godot_app`.

`android_release` and `ios_release` build an application and its debug symbols as
`godot_configured_app` does, under the settings of the `.bazelrc` configurations
`android-release`, `multi_abi` and `aab`, and of `ios-release`. Each also declares
`<name>.build_test`, which builds both, tagged with its mobile operating system, `android` or `ios`: CI's host jobs run it in the
same Bazel invocation and configuration as everything else (shared.bazelrc).
"""

load("@autoload_rules_godot//godot:app.bzl", "ANDROID_RELEASE", "APPLE_RELEASE", "godot_configured_app")
load("@bazel_skylib//rules:build_test.bzl", "build_test")

# A release derives its debug symbols from `app` and sets its platform itself.
_RELEASE_ATTRS = {
    "app": attr.label(doc = "The `godot_app`.", mandatory = True, configurable = False),
    "debug_symbols": None,
    "platform": None,
}

def _release(name, visibility, app, tags, settings, os_tag, test_compatible_with, **kwargs):
    """
    Declare a release and the test that builds it and its debug symbols.

    Args:
        name: the name of the release.
        visibility: the visibility of the release and its debug symbols.
        app: the `godot_app`.
        tags: the caller's tags, which add to `manual`.
        settings: the release settings. The caller's settings in `kwargs` win over them.
        os_tag: the mobile operating system the test is tagged with.
        test_compatible_with: the platforms the test can build on.
        **kwargs: the caller's other attributes of `godot_configured_app`.
    """
    godot_configured_app(
        name = name,
        visibility = visibility,
        app = app,
        debug_symbols = app.same_package_label(app.name + ".debug_symbols"),
        tags = ["manual"] + (tags or []),
        **(settings | {key: value for key, value in kwargs.items() if value != None})
    )

    # Building the release starts Godot.
    build_test(
        name = name + ".build_test",
        size = "small",
        tags = [os_tag, "godot_process"],
        target_compatible_with = test_compatible_with,
        targets = [":" + name, ":" + name + ".debug_symbols"],
    )

def _android_release_impl(name, visibility, app, tags, **kwargs):
    _release(
        name,
        visibility,
        app,
        tags,
        settings = ANDROID_RELEASE | {
            "android_format": "aab",
            "platform": Label("//examples:android_distribution"),
        },
        os_tag = "android",
        test_compatible_with = [],
        **kwargs
    )

android_release = macro(
    doc = """
    The multi-ABI release App Bundle of an application, with its debug symbols.

    The App Bundle is `<name>`, its debug symbols are `<name>.debug_symbols`, and the test
    that builds both is `<name>.build_test`. A setting the caller leaves unset takes its
    value from ANDROID_RELEASE. `tags` add to `manual`.
    """,
    implementation = _android_release_impl,
    inherit_attrs = godot_configured_app,
    attrs = _RELEASE_ATTRS | {"android_format": None},
)

def _ios_release_impl(name, visibility, app, tags, **kwargs):
    _release(
        name,
        visibility,
        app,
        tags,
        settings = APPLE_RELEASE | {
            "platform": Label("@autoload_rules_godot//godot/platforms:ios_sim_x86_64"),
        },
        os_tag = "ios",
        test_compatible_with = ["@platforms//os:macos"],
        **kwargs
    )

ios_release = macro(
    doc = """
    The release iOS Simulator application of the official templates, with its dSYMs.

    The application is `<name>`, its debug symbols are `<name>.debug_symbols`, and the test
    that builds both is `<name>.build_test`. A setting the caller leaves unset takes its
    value from APPLE_RELEASE. `tags` add to `manual`.
    """,
    implementation = _ios_release_impl,
    inherit_attrs = godot_configured_app,
    attrs = _RELEASE_ATTRS,
)
