"""
What the export's shell actions and an application's packaging actions read.

An edit reruns an action only when it changes one of the action's inputs, its arguments or a
file it reads that another action writes; it leaves the action cached otherwise. Each test
asserts both sides for the actions an edit must and must not rerun.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private/tests:action_inputs.bzl", "expect_not_read", "expect_reads", "godot_actions")
load("//godot/private/tests:pack_forms.bzl", "GODOT_EXPORT")
load(
    ":action_graph.bzl",
    "bundle_closure",
    "expect_same_actions",
    "is_compilation",
    "mentions",
    "reached",
    "reached_actions",
    "reads",
    "written_contents",
)
load(":android_settings.bzl", "ANDROID", "ANDROID_SDK", "MOBILE_FIXTURE")

visibility("private")

_EDITOR_PLUGIN_FIXTURE = "//godot/platforms/private/tests/fixtures/apps_with_editor_plugin_and_autoload:"
_MOBILE_PATH = "fixtures/mobile_app_with_platform_libraries/"

# A macOS application's shell files are written from the facts GodotShellAssets reports.
_MACOS = {"//command_line_option:platforms": str(Label("//godot/platforms:macos_arm64"))}
_MACOS_HOST = {"size": "small", "target_compatible_with": ["@platforms//os:macos"]}

# Apple applications need Xcode, which only a macOS host has.
_IOS = {"//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_x86_64"))}

# Imports, exports, extension descriptors and native compilation stay cached when only
# a platform library or platform resource changes.
_REUSED = (
    "GodotImport",
    "GodotPack",
    "GodotExport",
    "GodotExtensionDescriptors",
)

def _reused(mnemonic):
    return mnemonic.startswith(_REUSED) or is_compilation(mnemonic)

def _test_application_id_reaches_only_pack_and_shell_assets(name):
    analysis_test(
        name = name,
        targets = {
            "first": _EDITOR_PLUGIN_FIXTURE + "app",
            "second": _EDITOR_PLUGIN_FIXTURE + "other_app",
        },
        impl = _application_id_reaches_only_pack_and_shell_assets,
        config_settings = _MACOS | GODOT_EXPORT,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = _MACOS_HOST,
    )

def _application_id_reaches_only_pack_and_shell_assets(env, targets):
    for target, own, other in [
        (targets.first, "org.example.first", "org.example.second"),
        (targets.second, "org.example.second", "org.example.first"),
    ]:
        entries = reached(target)
        contents = written_contents(entries)
        for mnemonic in ["GodotPack", "GodotShellAssets"]:
            actions = [entry.action for entry in entries if entry.action.mnemonic == mnemonic]
            env.expect.where(mnemonic = mnemonic).that_collection(actions).has_size(1)
            for action in actions:
                env.expect.where(mnemonic = mnemonic, application_id = own).that_bool(
                    mentions(action, own, contents),
                ).equals(True)
                env.expect.where(mnemonic = mnemonic, application_id = other).that_bool(
                    mentions(action, other, contents),
                ).equals(False)

    # The project's imports, initialization and metadata index stay cached.
    expect_same_actions(env, targets.first, targets.second, _project_action)

def _project_action(entry):
    return entry.action.mnemonic.startswith("Godot") and entry.owner.endswith(":apps_with_editor_plugin_and_autoload")

# The shell-assets probe's configuration names no autoload, so the autoload's script
# reruns the export and leaves the probe cached (#129).
def _test_autoload_reaches_pack_but_no_shell_assets(name):
    analysis_test(
        name = name,
        target = _EDITOR_PLUGIN_FIXTURE + "pack",
        impl = _autoload_reaches_pack_but_no_shell_assets,
        config_settings = GODOT_EXPORT,
        extra_target_under_test_aspects = [godot_actions],
        attr_values = {"size": "small"},
    )

def _autoload_reaches_pack_but_no_shell_assets(env, target):
    path = "main/configuration.gd"
    expect_reads(env, target, "GodotPack", path)
    expect_not_read(env, target, ["GodotMetadataIndex", "GodotShellAssets"], path)

# An add-on's editor part, which registers an export plugin, reaches neither the export nor
# the shell-assets probe (D29).
def _test_editor_part_reaches_no_export(name):
    analysis_test(
        name = name,
        target = _EDITOR_PLUGIN_FIXTURE + "app",
        impl = _editor_part_reaches_no_export,
        config_settings = _MACOS,
        extra_target_under_test_aspects = [godot_actions],
        attr_values = _MACOS_HOST,
    )

def _editor_part_reaches_no_export(env, target):
    path = "addons/export_context/export_context.gd"
    expect_not_read(env, target, ["GodotMetadataIndex", "GodotPack", "GodotShellAssets"], path)

def _expect_library_source(env, target, active, inactive):
    entries = reached(target)
    env.expect.where(path = active).that_bool(
        any([reads(entry.action, active) for entry in entries]),
        expr = "an action reads the selected library source",
    ).equals(True)
    for entry in entries:
        env.expect.where(owner = entry.owner, mnemonic = entry.action.mnemonic, path = inactive).that_bool(
            reads(entry.action, inactive),
        ).equals(False)

def _test_android_app_reads_no_ios_library_source(name):
    analysis_test(
        name = name,
        target = MOBILE_FIXTURE + "app",
        impl = _android_app_reads_no_ios_library_source,
        config_settings = ANDROID,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = ANDROID_SDK,
    )

def _android_app_reads_no_ios_library_source(env, target):
    _expect_library_source(
        env,
        target,
        _MOBILE_PATH + "android/addon/src/org/example/addon/Addon.java",
        _MOBILE_PATH + "ios/Addon.swift",
    )

def _test_ios_app_reads_no_android_library_source(name):
    analysis_test(
        name = name,
        target = MOBILE_FIXTURE + "app",
        impl = _ios_app_reads_no_android_library_source,
        config_settings = _IOS,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = _MACOS_HOST,
    )

def _ios_app_reads_no_android_library_source(env, target):
    _expect_library_source(
        env,
        target,
        _MOBILE_PATH + "ios/Addon.swift",
        _MOBILE_PATH + "android/addon/src/org/example/addon/Addon.java",
    )

def _expect_bundle_inputs(env, target, changed, unchanged):
    """Assert that the changed files reach the bundle through no reused action, the others not at all."""
    closure = bundle_closure(target)
    entries = reached(target)
    for path in changed:
        env.expect.where(path = path).that_bool(
            any([candidate.endswith("/" + path) for candidate in closure.files]),
            expr = "the bundle is built from the file",
        ).equals(True)
        for entry in entries:
            if _reused(entry.action.mnemonic):
                env.expect.where(owner = entry.owner, mnemonic = entry.action.mnemonic, path = path).that_bool(
                    reads(entry.action, path),
                ).equals(False)
    for path in unchanged:
        env.expect.where(path = path).that_bool(
            any([candidate.endswith("/" + path) for candidate in closure.files]),
            expr = "the bundle is built from the file",
        ).equals(False)

def _test_ios_platform_inputs_reach_only_bundle_actions(name):
    analysis_test(
        name = name,
        target = MOBILE_FIXTURE + "app",
        impl = _ios_platform_inputs_reach_only_bundle_actions,
        config_settings = _IOS,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = _MACOS_HOST,
    )

def _ios_platform_inputs_reach_only_bundle_actions(env, target):
    _expect_bundle_inputs(
        env,
        target,
        changed = [
            # A platform library's resource and an application's platform resource.
            _MOBILE_PATH + "ios/composition_notice.txt",
            _MOBILE_PATH + "ios/app_notice.txt",
        ],
        unchanged = [_MOBILE_PATH + "android/composition/AndroidManifest.xml"],
    )

def _test_android_platform_inputs_reach_only_bundle_actions(name):
    analysis_test(
        name = name,
        target = MOBILE_FIXTURE + "app",
        impl = _android_platform_inputs_reach_only_bundle_actions,
        config_settings = ANDROID,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = ANDROID_SDK,
    )

def _android_platform_inputs_reach_only_bundle_actions(env, target):
    _expect_bundle_inputs(
        env,
        target,
        changed = [
            # A platform library's manifest and resource, and an application's platform
            # resource.
            _MOBILE_PATH + "android/composition/AndroidManifest.xml",
            _MOBILE_PATH + "android/composition/res/values/strings.xml",
            _MOBILE_PATH + "android/app/res/values/strings.xml",
        ],
        unchanged = [_MOBILE_PATH + "ios/Addon.swift"],
    )

    # A manifest placeholder value reaches the manifest merge, not the pack's export.
    value = "org.example.manifestvalues.scheme"
    entries = reached(target)
    contents = written_contents(entries)
    env.expect.where(value = value).that_bool(
        any([mentions(action, value, contents) for action in bundle_closure(target).actions]),
        expr = "a bundle action receives the manifest value",
    ).equals(True)
    for entry in entries:
        if _reused(entry.action.mnemonic):
            env.expect.where(owner = entry.owner, mnemonic = entry.action.mnemonic, value = value).that_bool(
                mentions(entry.action, value, contents),
            ).equals(False)

def shell_inputs_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_android_app_reads_no_ios_library_source,
            _test_android_platform_inputs_reach_only_bundle_actions,
            _test_application_id_reaches_only_pack_and_shell_assets,
            _test_autoload_reaches_pack_but_no_shell_assets,
            _test_editor_part_reaches_no_export,
            _test_ios_app_reads_no_android_library_source,
            _test_ios_platform_inputs_reach_only_bundle_actions,
        ],
    )
