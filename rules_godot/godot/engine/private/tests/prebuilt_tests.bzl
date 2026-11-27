"""Resolution of the root module's prebuilt hub registered through @godot//toolchains:all."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private/tests:engines.bzl", "ResolvedInfo")

visibility("private")

_PROBE = "//godot/engine/private/tests:probe"

def _test_prebuilt_hub_supplies_editor(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_prebuilt_hub_supplies_editor_impl,
    )

def _test_prebuilt_hub_supplies_editor_impl(env, target):
    editor = target[ResolvedInfo].editor
    env.expect.that_bool(
        editor != None,
        "the prebuilt hub supplies an editor for the execution platform",
    ).equals(True)
    if editor:
        env.expect.that_str(editor.provenance.kind).equals("prebuilt")
        env.expect.that_str(editor.provenance.version).equals("4.7.2")
        env.expect.that_str(Label(editor.provenance.component).repo_name.split("+")[-1]).equals("godot")
        env.expect.that_bool(
            editor.editor.executable != None,
            "the prebuilt editor is executable",
        ).equals(True)

def _test_prebuilt_hub_supplies_linux_runtime(name):
    analysis_test(
        name = name,
        target = _PROBE,
        impl = _test_prebuilt_hub_supplies_linux_runtime_impl,
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/engine/private/tests:linux_x86_64")),
        },
        # Fetches the prebuilt export templates; run explicitly.
        attr_values = {"tags": ["manual"]},
    )

def _test_prebuilt_hub_supplies_linux_runtime_impl(env, target):
    runtime = target[ResolvedInfo].runtime
    env.expect.that_bool(
        runtime != None,
        "the prebuilt hub supplies a Linux x86_64 release runtime",
    ).equals(True)
    if runtime:
        env.expect.that_str(Label(runtime.provenance.component).name).equals("runtime_linux_x86_64_release")
        env.expect.that_str(runtime.provenance.kind).equals("prebuilt")
        env.expect.that_str(runtime.runtime.version).equals("4.7.2")
        env.expect.that_str(runtime.runtime.variant).equals("release")

def prebuilt_test_suite(name):
    test_suite(
        name = name,
        tests = [_test_prebuilt_hub_supplies_editor],
    )

    # Manual, so outside the suite: a suite runs the tests it lists even when they are manual.
    _test_prebuilt_hub_supplies_linux_runtime(name = "test_prebuilt_hub_supplies_linux_runtime")
