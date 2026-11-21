"""
Which platform library compositions an application rejects during analysis.

An Android application fails for a selected input that is no Android library and for
manifest values whose keys the manifest merger treats as overrides, naming what owns each
value. An iOS application fails for a selected input of another operating system.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("//godot:app.bzl", "godot_app")
load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/private/config:application.bzl", "application_pack", "loadable_pack")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

_ANDROID_APPS = "//godot/platforms/private/tests/library_composition/fixtures/android_apps_with_transitive_platform_libraries:"
_IOS_APPS = "//godot/platforms/private/tests/library_composition/fixtures/ios_apps_with_transitive_platform_libraries:"

# Android applications analyze with the Android SDK and NDK toolchains that MODULE.bazel
# registers; rules_android's SDK has them only where it found one.
_ANDROID = struct(
    config_settings = {
        "//command_line_option:platforms": str(Label("//godot/platforms:android_arm64")),
    } | own_toolchains(),
    attr_values = {
        "size": "small",
        "target_compatible_with": ["//godot/platforms/private/tests:requires_android_sdk"],
    },
)

# The iOS backend needs a C/C++ toolchain for iOS, which only Xcode on a macOS host has.
_IOS = struct(
    config_settings = {
        "//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_x86_64")),
    },
    attr_values = {"size": "small", "target_compatible_with": ["@platforms//os:macos"]},
)

def _fails_with_message(env, target):
    env.expect.that_target(target).failures().contains_predicate(
        matching.contains(env.ctx.attr.message),
    )

def _failure_test(name, target, message, platform, config_settings = {}):
    analysis_test(
        name = name,
        target = target,
        impl = _fails_with_message,
        expect_failure = True,
        attrs = {"message": attr.string()},
        config_settings = platform.config_settings | config_settings,
        attr_values = platform.attr_values | {"message": message},
    )

def _test_android_app_rejects_unsupported_platform_input(name):
    godot_app(
        name = name + "_app",
        application_id = "org.example.composition.unsupported",
        pack = _ANDROID_APPS + "pack",
        platform_deps = [_ANDROID_APPS + "unsupported_input"],
        tags = ["manual"],
    )
    _failure_test(
        name = name,
        target = ":%s_app" % name,
        message = "Android platform_deps does not support input",
        platform = _ANDROID,
    )

# Keys the merger treats as overrides belong to a godot_app attribute or a pack setting; each
# diagnostic names that owner.
def _manifest_value_test(name, key, value, owner):
    godot_app(
        name = name + "_app",
        android_manifest_values = {key: value},
        application_id = "org.example.manifestvalues.reserved",
        pack = _ANDROID_APPS + "pack",
        tags = ["manual"],
    )
    _failure_test(
        name = name,
        target = ":%s_app" % name,
        message = owner,
        platform = _ANDROID,
    )

def _test_manifest_values_reject_application_id(name):
    _manifest_value_test(name, "applicationId", "org.example.other", "application_id")

def _test_manifest_values_reject_min_sdk(name):
    _manifest_value_test(name, "minSdkVersion", "26", "android_min_sdk_version")

def _test_manifest_values_reject_target_sdk(name):
    _manifest_value_test(name, "targetSdkVersion", "35", "android_target_sdk_version")

def _test_manifest_values_reject_version_code(name):
    _manifest_value_test(name, "versionCode", "7", "version/code")

def _test_manifest_values_reject_version_name(name):
    _manifest_value_test(name, "versionName", "1.0", "version/name")

def _test_manifest_values_reject_max_sdk(name):
    _manifest_value_test(name, "maxSdkVersion", "35", "an override godot_app does not expose")

def _test_ios_app_rejects_android_platform_input(name):
    godot_app(
        name = name + "_app",
        application_id = "org.example.composition.unsupported",
        pack = _IOS_APPS + "composition_base_pack",
        platform_deps = [_ANDROID_APPS + "composition"],
        tags = ["manual"],
    )
    _failure_test(
        name = name,
        target = ":%s_app" % name,
        message = "iOS platform_deps input",
        platform = _IOS,
    )

# FR-007, D8: an application delivers the platform libraries and Info.plist fragments of the
# add-ons of its start pack and of every pack it may load later, those the packs' resources
# use and those their projects name. godot_app passes its pack and loadable_packs to its
# application pack in this order, each loadable pack through loadable_pack; the
# build-output tests build the applications.
def _delivered_test(name, packs, platform, libraries, infoplists):
    loadable = []
    for index, pack in enumerate(packs[1:]):
        loadable_pack(name = "%s_loadable_%d" % (name, index), tags = ["manual"], deps = [pack])
        loadable.append(":%s_loadable_%d" % (name, index))
    application_pack(
        name = name + "_subject",
        application_id = "org.example.composition.loadable",
        tags = ["manual"],
        deps = packs[:1] + loadable,
    )
    analysis_test(
        name = name,
        target = name + "_subject",
        impl = _delivers,
        attrs = {"libraries": attr.string_list(), "infoplists": attr.string_list()},
        config_settings = platform.config_settings,
        attr_values = platform.attr_values | {"libraries": libraries, "infoplists": infoplists},
    )

def _delivers(env, target):
    project = target[GodotPackInfo].project
    env.expect.where(field = "platform_libraries").that_collection(
        [library.label.name for library in project.platform_libraries],
    ).contains_exactly(env.ctx.attr.libraries)
    env.expect.where(field = "infoplists").that_collection(
        [file.basename for file in project.infoplists.to_list()],
    ).contains_exactly(env.ctx.attr.infoplists)

def _test_android_app_delivers_libraries_of_loadable_packs(name):
    _delivered_test(name, [_ANDROID_APPS + "pack", _ANDROID_APPS + "composition_pack"], _ANDROID, ["addon_library", "composition", "plugin"], [])

def _test_ios_app_delivers_libraries_of_loadable_packs(name):
    _delivered_test(
        name,
        [_IOS_APPS + "composition_base_pack", _IOS_APPS + "composition_transitive_pack", _IOS_APPS + "pack"],
        _IOS,
        ["composition_resources", "controller", "swift"],
        ["addon.plist"],
    )

def library_composition_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_android_app_delivers_libraries_of_loadable_packs,
            _test_android_app_rejects_unsupported_platform_input,
            _test_manifest_values_reject_application_id,
            _test_manifest_values_reject_min_sdk,
            _test_manifest_values_reject_target_sdk,
            _test_manifest_values_reject_version_code,
            _test_manifest_values_reject_version_name,
            _test_manifest_values_reject_max_sdk,
            _test_ios_app_delivers_libraries_of_loadable_packs,
            _test_ios_app_rejects_android_platform_input,
        ],
    )
