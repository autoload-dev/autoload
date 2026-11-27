"""Which files an operation's initialization reads: its selection and what that depends on."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:providers.bzl", "GodotExtensionInfo")
load(":action_inputs.bzl", "actions_of", "expect_not_read", "expect_reads", "godot_actions")

visibility("private")

_FIXTURE = "//godot/private/tests/fixtures/project_with_shared_unit"

# FR-011 on both sides: a pack's initialization reads the scripts, scenes and assets of
# its selection and of what that depends on, and no file of the extension it contains,
# so a native edit reruns no initialization.
def _test_initialization_reads_the_selection_but_no_extension(name):
    analysis_test(
        name = name,
        targets = {
            "extension": _FIXTURE + ":hello",
            "pack": _FIXTURE + ":pack",
        },
        impl = _initialization_reads_the_selection_but_no_extension,
        extra_target_under_test_aspects = [godot_actions],
    )

def _initialization_reads_the_selection_but_no_extension(env, targets):
    pack = targets.pack
    env.expect.that_collection(actions_of(pack, "GodotInitialize"), expr = "GodotInitialize actions").has_size(1)
    for path in ["main/main.tscn", "main/state.gd", "main/home.gd", "main/home.svg", "main/icon.svg", "main/home_buffer.bin"]:
        expect_reads(env, pack, "GodotInitialize", path)
    extension = targets.extension[GodotExtensionInfo]
    files = extension.runtime_resource_paths.values() + extension.editor_resource_paths.values()
    env.expect.that_bool(len(files) > 1, expr = "the extension has files beside its descriptor").equals(True)
    for path in [file.short_path for file in files] + ["native/hello.cc"]:
        expect_not_read(env, pack, ["GodotInitialize"], path)

# A test of :home initializes over :home and :base only; the files of :main, which it does
# not select, are no input of its initialization.
def _test_initialization_reads_no_file_outside_the_selection(name):
    analysis_test(
        name = name,
        target = _FIXTURE + ":home_test",
        impl = _initialization_reads_no_file_outside_the_selection,
        extra_target_under_test_aspects = [godot_actions],
    )

def _initialization_reads_no_file_outside_the_selection(env, target):
    for path in ["main/home.gd", "main/icon.svg"]:
        expect_reads(env, target, "GodotInitialize", path)
    for path in ["main/main.tscn", "main/state.gd"]:
        expect_not_read(env, target, ["GodotInitialize"], path)

def initialization_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_initialization_reads_no_file_outside_the_selection,
            _test_initialization_reads_the_selection_but_no_extension,
        ],
    )
