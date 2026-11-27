"""Resolved components name their declaration, version, digest and customization."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private/tests:engines.bzl", "ResolvedInfo")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

visibility("private")

_PROBE = "//godot/engine/private/tests:probe"
_SOURCE_BUILT_SET = "//godot/engine/private/tests/fixtures/source_built_ios"

# iOS components apply Apple's aspects to their payload, which need macOS tools.
_MACOS_ONLY = {"target_compatible_with": ["@platforms//os:macos"]}

_MIXED = {
    "//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_arm64")),
    str(Label("//godot:variant")): "release",
} | own_toolchains([_SOURCE_BUILT_SET + ":all"])

def _expect_prebuilt_editor(env, editor):
    env.expect.that_bool(editor != None, "the hub editor must resolve").equals(True)
    if editor:
        provenance = editor.provenance
        env.expect.that_str(provenance.kind).equals("prebuilt")
        env.expect.that_str(provenance.version).equals("4.7.2")
        env.expect.that_bool(
            Label(provenance.component).repo_name.endswith("godot"),
            "the editor component's repository ends in godot",
        ).equals(True)

        # The editor archive's integrity pin identifies the acquired artifact.
        env.expect.that_bool(
            provenance.digest.startswith("sha"),
            "digest {} starts with sha".format(provenance.digest),
        ).equals(True)
        env.expect.that_dict(provenance.customizations).contains_exactly({})

def _expect_source_runtime(env, runtime):
    env.expect.that_bool(runtime != None, "the source-built runtime must resolve").equals(True)
    if runtime:
        provenance = runtime.provenance
        env.expect.that_str(provenance.kind).equals("source")
        env.expect.that_str(str(Label(provenance.component))).equals(
            str(Label(_SOURCE_BUILT_SET + ":runtime_ios_arm64_simulator_release")),
        )
        env.expect.that_str(provenance.digest).equals("sha256:0123")
        env.expect.that_collection(provenance.customizations["patches"]).contains_exactly(
            ["engine-name.patch"],
        ).in_order()

def _test_prebuilt_editor_names_its_artifact(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_prebuilt_editor_names_its_artifact_impl,
    )

def _test_prebuilt_editor_names_its_artifact_impl(env, target):
    _expect_prebuilt_editor(env, target[ResolvedInfo].editor)

def _test_source_runtime_names_its_recipe(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_source_runtime_names_its_recipe_impl,
        config_settings = _MIXED,
        attr_values = _MACOS_ONLY,
    )

def _test_source_runtime_names_its_recipe_impl(env, target):
    _expect_source_runtime(env, target[ResolvedInfo].runtime)

def _test_mixed_resolution_keeps_each_provenance(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_mixed_resolution_keeps_each_provenance_impl,
        config_settings = _MIXED,
        attr_values = _MACOS_ONLY,
    )

def _test_mixed_resolution_keeps_each_provenance_impl(env, target):
    # One resolution: the prebuilt hub's editor and the runtime of the source-built
    # registration set, each with its own provenance; neither is checked against the other.
    resolved = target[ResolvedInfo]
    _expect_prebuilt_editor(env, resolved.editor)
    _expect_source_runtime(env, resolved.runtime)

def provenance_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_prebuilt_editor_names_its_artifact,
            _test_source_runtime_names_its_recipe,
            _test_mixed_resolution_keeps_each_provenance,
        ],
    )
