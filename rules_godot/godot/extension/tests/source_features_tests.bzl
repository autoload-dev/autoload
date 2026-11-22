"""Source Godot feature tags and C++ toolchain features have independent contracts."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:providers.bzl", "GodotExtensionInfo")

_CcFeaturesInfo = provider(doc = "Requested Bazel features found on the real C++ dependency graph.", fields = ["features"])

def _cc_features_impl(_target, ctx):
    features = list(getattr(ctx.rule.attr, "features", []))
    dependencies = []
    for name in ["deps", "library", "tool_view"]:
        value = getattr(ctx.rule.attr, name, [])
        values = value if type(value) == "list" else [value] if value else []
        for dep in values:
            if _CcFeaturesInfo in dep:
                dependencies.append(dep[_CcFeaturesInfo].features)
    return [_CcFeaturesInfo(features = depset(features, transitive = dependencies))]

_cc_features = aspect(implementation = _cc_features_impl, attr_aspects = ["deps", "library", "tool_view"])

def _expect_source_tags(env, target, variant, expected_tags = None):
    tags = target[GodotExtensionInfo].library.tags
    if expected_tags:
        env.expect.that_str(tags).equals(expected_tags)
    env.expect.that_bool(tags.endswith("." + variant), expr = "Source tag must derive the Godot variant: " + tags).equals(True)

def _test_source_tags_derive_release_variant(name):
    analysis_test(
        name = name,
        target = ":automatic_fixture",
        impl = _test_source_tags_derive_release_variant_impl,
    )

def _test_source_tags_derive_release_variant_impl(env, target):
    _expect_source_tags(env, target, "release")

def _test_source_tags_derive_debug_variant(name):
    analysis_test(
        name = name,
        target = ":automatic_fixture",
        impl = _test_source_tags_derive_debug_variant_impl,
        config_settings = {str(Label("//godot:variant")): "debug"},
    )

def _test_source_tags_derive_debug_variant_impl(env, target):
    _expect_source_tags(env, target, "debug")

def _test_cc_features_stay_out_of_feature_tags(name):
    analysis_test(
        name = name,
        target = ":cc_features_fixture",
        impl = _test_cc_features_stay_out_of_feature_tags_impl,
        extra_target_under_test_aspects = [_cc_features],
    )

def _test_cc_features_stay_out_of_feature_tags_impl(env, target):
    env.expect.that_collection(target[_CcFeaturesInfo].features.to_list(), expr = "requested C++ features").contains(
        "rules_godot_cc_feature_probe",
    )
    tags = target[GodotExtensionInfo].library.tags
    env.expect.that_bool("rules_godot_cc_feature_probe" in tags, expr = "C++ feature in feature tags " + tags).equals(False)

# These iOS configurations need Apple's C++ toolchain, which only macOS execution platforms
# have. Wildcard runs on Linux keep the generic source and C++ feature cases.
def _test_ios_device_source_tags(name):
    analysis_test(
        name = name,
        target = ":automatic_fixture",
        impl = _test_ios_device_source_tags_impl,
        attr_values = {"target_compatible_with": ["@platforms//os:macos"]},
        config_settings = {"//command_line_option:platforms": str(Label("//godot/platforms:ios_arm64"))},
    )

def _test_ios_device_source_tags_impl(env, target):
    _expect_source_tags(env, target, "release", "ios.arm64.release")

def _test_ios_simulator_source_tags(name):
    analysis_test(
        name = name,
        target = ":automatic_fixture",
        impl = _test_ios_simulator_source_tags_impl,
        attr_values = {"target_compatible_with": ["@platforms//os:macos"]},
        config_settings = {"//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_arm64"))},
    )

def _test_ios_simulator_source_tags_impl(env, target):
    _expect_source_tags(env, target, "release", "ios.arm64.simulator.release")

def _test_editor_descriptors_keep_runtime_libraries_apart(name):
    analysis_test(
        name = name,
        target = "//godot/extension/tests/fixtures/c_abi:hello",
        impl = _test_editor_descriptors_keep_runtime_libraries_apart_impl,
    )

def _test_editor_descriptors_keep_runtime_libraries_apart_impl(env, target):
    extension = target[GodotExtensionInfo]
    tags = extension.library.tags
    env.expect.that_bool(tags.endswith(".release"), expr = "the runtime fragment lists the release library: " + tags).equals(True)
    descriptor = extension.descriptor_path
    env.expect.that_bool(
        extension.runtime_descriptor == extension.runtime_resource_paths.get(descriptor),
        expr = "descriptor_path names the runtime descriptor in runtime_resource_paths",
    ).equals(True)
    runtime = {file: True for file in extension.runtime_resource_paths.values()}
    for name, editor in [
        ("editor_resource_paths", extension.editor_resource_paths),
        ("host_editor_resource_paths", extension.host_editor_resource_paths),
    ]:
        env.expect.that_bool(
            editor.get(descriptor) not in [None, extension.runtime_descriptor],
            expr = name + " holds the tool view's fragment at the descriptor's path",
        ).equals(True)
        env.expect.that_bool(
            bool([path for path in editor if path != descriptor and path.split("/")[-2].endswith(".editor")]),
            expr = name + " holds a library of the tool configuration",
        ).equals(True)
        env.expect.that_bool(
            bool([file for file in editor.values() if file in runtime]),
            expr = name + " shares a file with runtime_resource_paths",
        ).equals(False)

def source_features_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_source_tags_derive_release_variant,
            _test_source_tags_derive_debug_variant,
            _test_cc_features_stay_out_of_feature_tags,
            _test_ios_device_source_tags,
            _test_ios_simulator_source_tags,
            _test_editor_descriptors_keep_runtime_libraries_apart,
        ],
    )
