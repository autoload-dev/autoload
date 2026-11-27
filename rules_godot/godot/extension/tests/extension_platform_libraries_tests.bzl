"""
Platform payload of an extension: its configurable platform libraries retain their real
provider edge, and its Info.plist fragments reach applications by itself and through an
add-on.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:defs.bzl", "godot_addon")
load("//godot/extension:defs.bzl", "godot_extension")
load("//godot/private:providers.bzl", "GodotAddonInfo", "GodotExtensionInfo")

visibility("private")

def _test_platform_libraries_keep_provider_edge(name):
    analysis_test(
        name = name,
        target = ":platform_library_extension",
        impl = _test_platform_libraries_keep_provider_edge_impl,
    )

def _test_platform_libraries_keep_provider_edge_impl(env, target):
    extension = target[GodotExtensionInfo]
    env.expect.that_collection(
        [dependency.label.name for dependency in extension.platform_libraries],
        expr = "platform_libraries",
    ).contains_exactly(["private_platform_library"]).in_order()
    env.expect.that_collection(
        [file.basename for file in target[DefaultInfo].files.to_list()],
        expr = "default outputs",
    ).contains("platform_library_extension.gdextension")

# An extension states the Info.plist keys its native code needs, used by itself or in an
# add-on's deps.
def _test_infoplists_reach_the_addons_contributions(name):
    godot_extension(
        name = name + "_extension",
        entry_symbol = "plist_fixture_init",
        infoplists = ["extension_fixture.plist"],
        library = ":android_fixture",
        tags = ["manual"],
    )
    godot_addon(
        name = name + "_addon",
        tags = ["manual"],
        deps = [":" + name + "_extension"],
    )
    analysis_test(
        name = name,
        targets = {
            "extension": name + "_extension",
            "addon": name + "_addon",
        },
        impl = _infoplists_reach_the_addons_contributions,
    )

def _infoplists_reach_the_addons_contributions(env, targets):
    for each in ["extension", "addon"]:
        env.expect.where(target = each).that_collection(
            [file.basename for file in getattr(targets, each)[GodotAddonInfo].platform_contributions.infoplists.to_list()],
        ).contains_exactly(["extension_fixture.plist"])

def extension_platform_libraries_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_infoplists_reach_the_addons_contributions,
            _test_platform_libraries_keep_provider_edge,
        ],
    )
