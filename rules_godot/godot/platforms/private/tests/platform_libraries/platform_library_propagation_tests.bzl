"""
How add-ons' platform libraries and extension libraries reach an application.

A pack collects the platform libraries and Info.plist fragments of its add-ons; an iOS
application links them and the static library each extension configures for its platform
slice, but not the dynamic framework of one, which Godot loads; an Android application
collects each extension's library for its ABI, with its runtime dependencies. An extension
without a library for the application's operating system delivers none; a library iOS
cannot link, or two Android libraries of one name, fail the application's analysis. The
tests pin the export platform, arm64 Android or arm64 iOS devices, so they expect the same
libraries on every host that runs them.
"""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/platforms/private/tests:action_graph.bzl", "reached", "reached_actions")
load("//godot/platforms/private/tests:backends.bzl", "godot_android_application", "godot_ios_application")
load("//godot/private/tests:configurations.bzl", "in_platform_slice")

_ADDONS = "//godot/platforms/private/tests/platform_libraries/fixtures/addons_with_platform_libraries:"
_UNMATCHED = "//godot/platforms/private/tests/platform_libraries/fixtures/extensions_without_matching_libraries:"
_DECLARATIONS = "//godot/platforms/private/tests/platform_libraries/fixtures/extension_library_declarations:"
_LINKED_FRAMEWORKS = "//godot/platforms/private/tests/platform_libraries/fixtures/linked_frameworks:"

# The configuration settings and test attributes of each target platform.
_HOST = struct(config_settings = {}, attr_values = {"size": "small"})

# Without an Android C/C++ toolchain, the extension libraries are packaged unstripped.
_ANDROID = struct(
    config_settings = {
        "//command_line_option:platforms": str(Label("//godot/platforms:android_arm64")),
        "//command_line_option:strip": "never",
    },
    attr_values = {"size": "small"},
)

# The iOS backend needs a C/C++ toolchain for iOS, which only Xcode on a macOS host has.
_IOS = struct(
    config_settings = {"//command_line_option:platforms": str(Label("//godot/platforms:ios_arm64"))},
    attr_values = {"size": "small", "target_compatible_with": ["@platforms//os:macos"]},
)

def _android_libraries(name, fixture, pack):
    """Arrange an Android application of pack and return its extension libraries target."""
    godot_android_application(
        name = name + "_app",
        application_id = "org.example.game",
        pack = fixture + pack,
        runtime = fixture + "runtime",
        tags = ["manual"],
    )
    return ":%s_app.godot_jni_libraries" % name

def _ios_app(name, fixture, pack, part = ""):
    """
    Arrange an iOS application of pack and return its shell target or a part of the shell.

    The part is analyzed in the application's platform slice, where rules_apple's split
    analyzes it, not in the test's own configuration with a macOS CPU name.
    """
    godot_ios_application(
        name = name + "_app",
        bundle_id = "org.example.game",
        pack = fixture + pack,
        runtime = fixture + "runtime",
        tags = ["manual"],
    )
    in_platform_slice(
        name = name + "_in_platform_slice",
        tags = ["manual"],
        target = ":%s_app.godot_shell%s" % (name, part),
    )
    return ":%s_in_platform_slice" % name

# A whole iOS application: the simulator needs no provisioning profile.
_IOS_SIMULATOR = struct(
    config_settings = {"//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_arm64"))},
    attr_values = _IOS.attr_values,
)

def _ios_libraries(name, fixture, pack):
    """Arrange an iOS application of pack and return its extension libraries target."""
    return _ios_app(name, fixture, pack, ".extension_libraries")

def _linked(target):
    """Names of the owners of the libraries a CcInfo links."""
    return [
        linker_input.owner.name
        for linker_input in target[CcInfo].linking_context.linker_inputs.to_list()
    ]

def _fails_with_messages(env, target):
    failures = env.expect.that_target(target).failures()
    for message in env.ctx.attr.messages:
        failures.contains_predicate(matching.contains(message))

def _failure_test(name, target, messages, platform):
    analysis_test(
        name = name,
        target = target,
        impl = _fails_with_messages,
        expect_failure = True,
        attrs = {"messages": attr.string_list()},
        config_settings = platform.config_settings,
        attr_values = platform.attr_values | {"messages": messages},
    )

def _analyzes(_env, _target):
    pass

def _analyzes_test(name, target, platform):
    analysis_test(
        name = name,
        target = target,
        impl = _analyzes,
        config_settings = platform.config_settings,
        attr_values = platform.attr_values,
    )

# Applications read them from the project of the pack's platform slice.
def _test_project_collects_addon_platform_libraries(name):
    analysis_test(
        name = name,
        target = _ADDONS + "pack",
        impl = _project_collects_addon_platform_libraries,
        attr_values = _HOST.attr_values,
    )

def _project_collects_addon_platform_libraries(env, target):
    project = target[GodotPackInfo].project
    env.expect.that_collection(
        [library.label.name for library in project.platform_libraries],
        expr = "platform_libraries",
    ).contains_exactly(["addon_apple", "addon_java", "extension_apple", "utility_apple"]).in_order()
    env.expect.that_collection(
        [file.basename for file in project.infoplists.to_list()],
        expr = "infoplists",
    ).contains_exactly(["addon.plist"]).in_order()

def _test_ios_app_links_addon_platform_libraries(name):
    analysis_test(
        name = name,
        target = _ios_libraries(name, _ADDONS, "pack"),
        impl = _ios_app_links_addon_platform_libraries,
        config_settings = _IOS.config_settings,
        attr_values = _IOS.attr_values,
    )

def _ios_app_links_addon_platform_libraries(env, target):
    env.expect.that_collection(_linked(target), expr = "linked libraries").contains_at_least(
        ["addon_apple", "extension_apple", "utility_apple"],
    )

def _test_ios_app_links_extension_library_of_its_platform_slice(name):
    analysis_test(
        name = name,
        target = _ios_libraries(name, _ADDONS, "pack"),
        impl = _ios_app_links_extension_library_of_its_platform_slice,
        config_settings = _IOS.config_settings,
        attr_values = _IOS.attr_values,
    )

def _ios_app_links_extension_library_of_its_platform_slice(env, target):
    linked = env.expect.that_collection(_linked(target), expr = "linked libraries")
    linked.contains("ios_arm_library")
    linked.not_contains("ios_x86_library")

def _test_ios_app_links_no_extension_framework(name):
    analysis_test(
        name = name,
        target = _ios_libraries(name, _DECLARATIONS, "framework_ios_extension_pack"),
        impl = _ios_app_links_no_extension_framework,
        config_settings = _IOS.config_settings,
        attr_values = _IOS.attr_values,
    )

def _ios_app_links_no_extension_framework(env, target):
    flags = [
        flag
        for linker_input in target[CcInfo].linking_context.linker_inputs.to_list()
        for flag in linker_input.user_link_flags
    ]
    env.expect.that_collection(flags, expr = "link flags").not_contains("-Wl,-u,_framework_ios_init")
    env.expect.that_collection(_linked(target), expr = "linked libraries").not_contains("framework")

def _test_ios_app_embeds_linked_frameworks_once(name):
    godot_ios_application(
        name = name + "_app",
        bundle_id = "org.example.game",
        pack = _LINKED_FRAMEWORKS + "pack",
        runtime = _LINKED_FRAMEWORKS + "runtime",
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = name + "_app",
        impl = _ios_app_embeds_linked_frameworks_once,
        config_settings = _IOS_SIMULATOR.config_settings,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = _IOS_SIMULATOR.attr_values,
    )

def _ios_app_embeds_linked_frameworks_once(env, target):
    # rules_apple embeds and signs each framework with one action.
    embedded = [
        {
            part: None
            for file in entry.action.inputs.to_list()
            for part in file.path.split("/")
            if part.endswith(".framework")
        }.keys()
        for entry in reached(target)
        if entry.action.mnemonic == "ImportedDynamicFrameworkProcessor"
    ]
    env.expect.that_collection(embedded, expr = "frameworks of each embedding action").contains_exactly([
        ["analytics_extension.framework"],
        ["core_extension.framework"],
        ["FixtureAnalytics.framework"],
        ["FixtureCore.framework"],
    ])

def _test_ios_shell_merges_addon_infoplists(name):
    analysis_test(
        name = name,
        target = _ios_app(name, _ADDONS, "pack"),
        impl = _ios_shell_merges_addon_infoplists,
        config_settings = _IOS.config_settings,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = _IOS.attr_values,
    )

def _ios_shell_merges_addon_infoplists(env, target):
    inputs = [
        file.basename
        for entry in reached(target)
        if entry.action.mnemonic == "GodotShellFile"
        for file in entry.action.inputs.to_list()
    ]

    # The strict shell metadata merger consumes the contributed fragment.
    env.expect.that_collection(inputs, expr = "GodotShellFile inputs").contains("addon.plist")
    env.expect.that_collection(
        [file.basename for file in target[OutputGroupInfo].plist.to_list()],
        expr = "plist output group",
    ).contains_exactly(["Godot.plist"])

# An extension without a library for the operating system delivers none.

def _test_android_app_of_desktop_extension_analyzes(name):
    _analyzes_test(name, _android_libraries(name, _UNMATCHED, "desktop_pack"), _ANDROID)

def _test_ios_app_of_desktop_extension_analyzes(name):
    _analyzes_test(name, _ios_libraries(name, _UNMATCHED, "desktop_pack"), _IOS)

def _test_ios_app_without_static_archive_fails(name):
    _failure_test(
        name,
        _ios_libraries(name, _DECLARATIONS, "shared_ios_extension_pack"),
        ["shared_ios_extension: ", "is a dynamic library, which ios arm64 device cannot load"],
        _IOS,
    )

def _jni_libraries_test(name, pack, count):
    analysis_test(
        name = name,
        target = _android_libraries(name, _DECLARATIONS, pack),
        impl = _android_app_collects_unique_jni_libraries,
        attrs = {"count": attr.int()},
        config_settings = _ANDROID.config_settings,
        attr_values = _ANDROID.attr_values | {"count": count},
    )

def _android_app_collects_unique_jni_libraries(env, target):
    manifests = [
        json.decode(action.content)
        for action in target.actions
        if action.mnemonic == "FileWrite" and
           action.outputs.to_list()[0].basename.endswith(".jni.json")
    ]
    env.expect.that_int(len(manifests), expr = "JNI manifests").equals(1)
    entries = manifests[0] if manifests else []
    env.expect.that_int(len(entries), expr = "JNI entries").equals(env.ctx.attr.count)
    paths = [
        entry["abi"] + "/" + entry.get("name", entry["source"].rsplit("/", 1)[-1])
        for entry in entries
    ]
    env.expect.that_int(len({path: True for path in paths}), expr = "distinct JNI paths").equals(len(paths))

def _test_android_app_collects_runtime_dependency_beside_library(name):
    _jni_libraries_test(name, "android_dependency_extension_pack", 2)

def _test_android_libraries_with_one_file_name_fail(name):
    _failure_test(
        name,
        _android_libraries(name, _DECLARATIONS, "android_collision_pack"),
        ["duplicate Android library:", "libcollision.so"],
        _ANDROID,
    )

def platform_library_propagation_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_android_app_collects_runtime_dependency_beside_library,
            _test_android_app_of_desktop_extension_analyzes,
            _test_android_libraries_with_one_file_name_fail,
            _test_ios_app_embeds_linked_frameworks_once,
            _test_ios_app_links_no_extension_framework,
            _test_ios_app_links_addon_platform_libraries,
            _test_ios_app_links_extension_library_of_its_platform_slice,
            _test_ios_app_of_desktop_extension_analyzes,
            _test_ios_app_without_static_archive_fails,
            _test_ios_shell_merges_addon_infoplists,
            _test_project_collects_addon_platform_libraries,
        ],
    )
