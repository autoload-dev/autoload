"""
Which version and build number shell files and packs take under the release build settings.

A release pipeline sets `//godot:app_version` and `//godot:build_number` without editing
BUILD files. The shell file writers prefer the version export options a pack sets, and a
pack prefers its own `application/config/version` setting.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/platforms/private/tests:action_graph.bzl", "reached", "reached_actions", "written_contents")
load("//godot/platforms/private/tests:backends.bzl", "godot_android_application", "godot_ios_application")

_FIXTURE = "//godot/platforms/private/tests/export_settings/fixtures/packs_with_and_without_version_options:"

_RELEASE_SETTINGS = {
    str(Label("//godot:app_version")): "2.3.4",
    str(Label("//godot:build_number")): 57,
}

def _written(env, target, suffix):
    """Return the text that the actions the target reaches write to a file ending in suffix."""
    contents = [
        text
        for path, text in written_contents(reached(target)).items()
        if path.endswith(suffix)
    ]
    env.expect.where(suffix = suffix).that_collection(contents).has_size(1)
    return contents[0] if contents else ""

def _expect_written(env, target, suffix, expected):
    content = _written(env, target, suffix)
    for text in expected:
        env.expect.that_str(content).contains(text)

def _android_bootstrap(name, pack):
    godot_android_application(
        name = name + "_app",
        application_id = "org.example.game",
        pack = _FIXTURE + pack,
        runtime = _FIXTURE + "runtime",
        tags = ["manual"],
    )
    return ":" + name + "_app.godot_bootstrap"

def _ios_shell(name, pack):
    godot_ios_application(
        name = name + "_app",
        bundle_id = "org.example.game",
        pack = _FIXTURE + pack,
        runtime = _FIXTURE + "runtime",
        tags = ["manual"],
    )
    return ":" + name + "_app.godot_shell"

# The shell and bootstrap write their settings in any configuration, so the tests keep the
# host's and run on every host, rather than a platform slice of an Android or iOS export
# platform (//godot/private/tests:configurations.bzl), which needs that SDK.
def _release_test(name, target, impl):
    analysis_test(
        name = name,
        target = target,
        impl = impl,
        config_settings = _RELEASE_SETTINGS,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = {"size": "small"},
    )

def _test_android_release_settings(name):
    _release_test(name, _android_bootstrap(name, "android_pack"), _android_release_settings)

def _android_release_settings(env, target):
    _expect_written(env, target, "AndroidManifest.xml.json", [
        '"explicit":[]',
        '"app_version":"2.3.4"',
        '"build_number":57',
    ])

def _test_android_explicit_version(name):
    _release_test(name, _android_bootstrap(name, "android_versioned_pack"), _android_explicit_version)

def _android_explicit_version(env, target):
    _expect_written(env, target, "AndroidManifest.xml.json", ['"version/code","version/name"'])

def _test_ios_release_settings(name):
    _release_test(name, _ios_shell(name, "ios_pack"), _ios_release_settings)

def _ios_release_settings(env, target):
    _expect_written(env, target, "Godot.plist.json", [
        '"app_version":"2.3.4"',
        '"build_number":57',
    ])

def _test_ios_explicit_version(name):
    _release_test(name, _ios_shell(name, "ios_versioned_pack"), _ios_explicit_version)

def _ios_explicit_version(env, target):
    _expect_written(env, target, "Godot.plist.json", ['"application/short_version","application/version"'])

def _expect_pack_version(env, target, expected):
    data = json.decode(_written(env, target, ".pack.config.json") or "{}")
    env.expect.that_str(data.get("settings", {}).get("application/config/version", "")).equals(expected)

def _test_pack_release_settings(name):
    _release_test(name, _FIXTURE + "pack", _pack_release_settings)

def _pack_release_settings(env, target):
    _expect_pack_version(env, target, '"2.3.4"')

def _test_pack_explicit_version(name):
    _release_test(name, _FIXTURE + "pack_with_version_setting", _pack_explicit_version)

def _pack_explicit_version(env, target):
    _expect_pack_version(env, target, '"9.9"')

def export_settings_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_android_explicit_version,
            _test_android_release_settings,
            _test_ios_explicit_version,
            _test_ios_release_settings,
            _test_pack_explicit_version,
            _test_pack_release_settings,
        ],
    )
