"""
How an application's own files replace the shell defaults of its Android or iOS shell.

An override reaches the platform rule unchanged and the shell leaves out its default for the
same slot; an application without overrides keeps the shell it had.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private/tests:action_inputs.bzl", "expect_not_read", "godot_actions")
load(":action_graph.bzl", "bundle_closure", "reached", "reached_actions", "reads")
load(":android_settings.bzl", "ANDROID", "ANDROID_SDK")

visibility("private")

_FIXTURE = "//godot/platforms/private/tests/fixtures/mobile_app_with_platform_libraries:"
_PATH = "fixtures/mobile_app_with_platform_libraries/"
_ANDROID_OVERRIDES = _PATH + "android/overrides/"
_IOS_OVERRIDES = _PATH + "ios/overrides/"

# Apple applications need Xcode, which only a macOS host has.
_IOS = {"//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_x86_64"))}
_MACOS_HOST = {"size": "small", "target_compatible_with": ["@platforms//os:macos"]}

# The actions of the pack's export, which overrides must leave cached.
_EXPORT = ["GodotExportOptions", "GodotImport", "GodotPack", "GodotPackSelection", "GodotShellAssets"]

def _shell_actions(target):
    """
    Return the shell writers and yields a target reaches.

    An action reached along several dependency paths or configurations counts once.

    Args:
        target: The target under test, analyzed with the reached_actions aspect.

    Returns:
        struct(writers, yields): the GodotShellFile actions by command, as a dict of
        lists, and the GodotShellYield actions.
    """
    actions = _unique_shell_actions(target)
    writers = {}
    for action in actions:
        if action.mnemonic == "GodotShellFile":
            # The command is the first argument after the tool.
            writers.setdefault(action.argv[1], []).append(action)
    yields = [action for action in actions if action.mnemonic == "GodotShellYield"]
    return struct(writers = writers, yields = yields)

def _unique_shell_actions(target):
    """Return the GodotShellFile and GodotShellYield actions a target reaches, once per output."""
    actions = {
        entry.action.outputs.to_list()[0].short_path: entry.action
        for entry in reached(target)
        if entry.action.mnemonic in ["GodotShellFile", "GodotShellYield"]
    }
    return actions.values()

def _expect_closure(env, target, present, absent):
    """Assert which files the target's bundle is built from."""
    files = bundle_closure(target).files
    for path, expected in [(path, True) for path in present] + [(path, False) for path in absent]:
        env.expect.where(path = path).that_bool(
            any([file.endswith(path) for file in files]),
            expr = "the bundle is built from the file",
        ).equals(expected)

def _analysis_test(name, target, impl, android, config_settings = {}):
    analysis_test(
        name = name,
        target = _FIXTURE + target,
        impl = impl,
        config_settings = (ANDROID if android else _IOS) | config_settings,
        extra_target_under_test_aspects = [reached_actions, godot_actions],
        attr_values = ANDROID_SDK if android else _MACOS_HOST,
    )

def _test_android_application_without_overrides_keeps_its_shell(name):
    _analysis_test(name, "app", _android_application_without_overrides_keeps_its_shell, android = True)

def _android_application_without_overrides_keeps_its_shell(env, target):
    shell = _shell_actions(target)
    env.expect.that_collection(shell.yields).has_size(0)
    env.expect.that_collection(shell.writers.get("android-main-manifest", [])).has_size(0)
    manifests = shell.writers["android-manifest"]
    env.expect.that_collection(manifests).has_size(1)
    for action in manifests:
        env.expect.that_str(action.outputs.to_list()[0].short_path).contains(
            ".godot_bootstrap/AndroidManifest.xml",
        )
    _expect_closure(env, target, present = [], absent = [".godot_bootstrap/shell/AndroidManifest.xml"])

def _test_android_overrides_replace_shell_defaults(name):
    _analysis_test(name, "app_with_overrides", _android_overrides_replace_shell_defaults, android = True)

def _android_overrides_replace_shell_defaults(env, target):
    shell = _shell_actions(target)

    # The launcher icon reaches the yield of the icon tree, the drawable that of the splash
    # tree; each yield reads only the resources of its type.
    env.expect.that_collection(shell.yields).has_size(2)
    for action in shell.yields:
        overridden = [
            action.argv[index + 1]
            for index, argument in enumerate(action.argv)
            if argument == "--override"
        ]
        env.expect.that_int(len(overridden)).equals(1)

    # The themes writer reads the unqualified value resources, not the drawable.
    themes = shell.writers["android-themes"]
    env.expect.that_collection(themes).has_size(1)
    for action in themes:
        env.expect.that_bool(reads(action, _ANDROID_OVERRIDES + "res/values/themes.xml")).equals(True)
        env.expect.that_bool(reads(action, _ANDROID_OVERRIDES + "res/drawable/start.xml")).equals(False)

    # The application's manifest becomes the main manifest; the shell manifest moves into
    # a library below it.
    main = shell.writers["android-main-manifest"]
    env.expect.that_collection(main).has_size(1)
    for action in main:
        env.expect.that_bool(reads(action, _ANDROID_OVERRIDES + "AndroidManifest.xml")).equals(True)
    manifests = shell.writers["android-manifest"]
    env.expect.that_collection(manifests).has_size(1)
    for action in manifests:
        env.expect.that_str(action.outputs.to_list()[0].short_path).contains(
            ".godot_bootstrap/shell/AndroidManifest.xml",
        )
    _expect_closure(
        env,
        target,
        present = [
            ".godot_bootstrap/shell/AndroidManifest.xml",
            _ANDROID_OVERRIDES + "res/drawable/start.xml",
            _ANDROID_OVERRIDES + "res/mipmap-xxxhdpi/icon.png",
            _ANDROID_OVERRIDES + "res/values/themes.xml",
        ],
        absent = [],
    )

    # The pack's export reads none of them.
    for path in ["AndroidManifest.xml", "res/values/themes.xml", "res/mipmap-xxxhdpi/icon.png"]:
        expect_not_read(env, target, _EXPORT, _ANDROID_OVERRIDES + path)

def _test_android_bundle_carries_the_shell_manifest_library(name):
    _analysis_test(
        name,
        "app_with_overrides",
        _android_bundle_carries_the_shell_manifest_library,
        android = True,
        config_settings = {str(Label("//godot:android_format")): "aab"},
    )

def _android_bundle_carries_the_shell_manifest_library(env, target):
    # The App Bundle's base module merges the same manifests as the APK.
    env.expect.that_collection(_shell_actions(target).writers["android-main-manifest"]).has_size(1)
    _expect_closure(
        env,
        target,
        present = [
            ".godot_bootstrap/shell/AndroidManifest.xml",
            _ANDROID_OVERRIDES + "res/values/themes.xml",
        ],
        absent = [],
    )

def _test_ios_application_without_overrides_keeps_its_shell(name):
    _analysis_test(name, "app", _ios_application_without_overrides_keeps_its_shell, android = False)

def _ios_application_without_overrides_keeps_its_shell(env, target):
    plists = _shell_actions(target).writers["ios-plist"]
    env.expect.that_collection(plists).has_size(1)
    for action in plists:
        env.expect.that_collection(action.argv).not_contains("--override")
    _expect_closure(
        env,
        target,
        present = [
            ".godot_shell/PrivacyInfo.xcprivacy",
            ".godot_shell/LaunchScreen.xcassets/Contents.json",
            ".ios/Assets.xcassets/AppIcon.appiconset/Contents.json",
        ],
        absent = [_IOS_OVERRIDES + "Overrides.plist"],
    )

def _test_ios_overrides_replace_shell_defaults(name):
    _analysis_test(name, "app_with_overrides", _ios_overrides_replace_shell_defaults, android = False)

def _ios_overrides_replace_shell_defaults(env, target):
    # The Info.plist writer reads the application's fragment and leaves out its keys.
    plists = _shell_actions(target).writers["ios-plist"]
    env.expect.that_collection(plists).has_size(1)
    for action in plists:
        env.expect.that_bool(reads(action, _IOS_OVERRIDES + "Overrides.plist")).equals(True)
    _expect_closure(
        env,
        target,
        present = [
            _IOS_OVERRIDES + "Overrides.plist",
            _IOS_OVERRIDES + "PrivacyInfo.xcprivacy",
            _IOS_OVERRIDES + "LaunchScreen.storyboard",
            _IOS_OVERRIDES + "Assets.xcassets/AppIcon.appiconset/icon_1024.png",
        ],
        absent = [
            # The privacy manifest, launch screen and app icons the shell would write.
            ".godot_shell/PrivacyInfo.xcprivacy",
            ".godot_shell/LaunchScreen.xcassets/Contents.json",
            ".ios/Assets.xcassets/AppIcon.appiconset/Contents.json",
        ],
    )

def shell_overrides_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_android_application_without_overrides_keeps_its_shell,
            _test_android_bundle_carries_the_shell_manifest_library,
            _test_android_overrides_replace_shell_defaults,
            _test_ios_application_without_overrides_keeps_its_shell,
            _test_ios_overrides_replace_shell_defaults,
        ],
    )
