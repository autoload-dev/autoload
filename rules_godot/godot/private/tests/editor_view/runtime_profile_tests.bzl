"""The derivation, writer and test godot_runtime_profile declares, and what each is given."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "subjects")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot:defs.bzl", "godot_runtime_profile")
load("//godot/private:view.bzl", "GodotViewInfo")
load("//godot/private/tests:manifests.bzl", "manifest_content")

visibility("private")

_FIXTURE = "//godot/private/tests/editor_view/fixtures/project_edited_in_the_view"
_PACKAGE = "godot/private/tests/editor_view"
_CHECKED_IN = "runtime_profile/checked_in"

def _profile(name, **kwargs):
    godot_runtime_profile(
        name = name + "_profile",
        project = _FIXTURE,
        deps = [_FIXTURE + ":main"],
        profile = kwargs.pop("profile", name + ".gdbuild"),
        tags = ["manual"],
        **kwargs
    )
    base = name + "_profile"
    return {
        "derived": base + ".derived",
        "test": base + ".test",
        "view": base + ".view",
        "writer": base,
    }

def _derivation(target):
    return manifest_content(target, ".derive.json")

def _editor_of(target):
    """The editor executable the derivation's action starts."""
    actions = [
        action
        for action in target[TestingAspectInfo].actions
        if action.mnemonic == "GodotRuntimeProfile"
    ]
    if len(actions) != 1:
        fail("expected one GodotRuntimeProfile action, found %d" % len(actions))
    argv = actions[0].argv
    return argv[argv.index("--editor") + 1]

# The editor opens the project as an editor view stages it; the editor tool derives it.
def _test_the_derivation_runs_the_editor_over_the_view(name):
    analysis_test(
        name = name,
        targets = _profile(name, keep_classes = ["Camera3D"]),
        impl = _the_derivation_runs_the_editor_over_the_view,
    )

def _the_derivation_runs_the_editor_over_the_view(env, targets):
    view = targets.view[GodotViewInfo]
    manifest = _derivation(targets.derived)
    env.expect.that_str(manifest["project_file"]).equals(view.editor_project_file.path)
    env.expect.that_collection(manifest["member_resource_paths"].keys()).contains_at_least(
        ["main/main.gd"],
    )

# The ruleset's classes and the target's own are kept, each once.
def _test_the_keep_list_joins_the_ruleset_list_and_the_targets(name):
    analysis_test(
        name = name,
        targets = _profile(name, keep_classes = ["Camera3D", "Image"]),
        impl = _the_keep_list_joins_the_ruleset_list_and_the_targets,
    )

def _the_keep_list_joins_the_ruleset_list_and_the_targets(env, targets):
    manifest = _derivation(targets.derived)
    keep = manifest["keep_classes"]
    env.expect.that_collection(keep).contains_at_least(["Camera3D", "Image", "Script", "Shader"])
    env.expect.that_bool(keep == sorted(keep)).equals(True)
    env.expect.that_int(len([name for name in keep if name == "Image"])).equals(1)

# The engine attribute selects the editor that detects, as it does for other operations.
def _test_the_engine_selects_the_editor(name):
    analysis_test(
        name = name,
        targets = {
            "default": _profile(name + "_default")["derived"],
            "named": _profile(name + "_named", engine = "beta")["derived"],
        },
        impl = _the_engine_selects_the_editor,
    )

def _the_engine_selects_the_editor(env, targets):
    env.expect.that_str(_editor_of(targets.named)).contains("+beta_editor_")
    env.expect.that_bool("+beta_editor_" in _editor_of(targets.default)).equals(False)

# <name> writes the profile and <name>.test compares it; both name the writer, which the
# test's report tells the user to run.
def _test_the_writer_and_test_list_the_file_they_place(name):
    analysis_test(
        name = name,
        targets = _profile(name, profile = _CHECKED_IN + ".gdbuild"),
        impl = _the_writer_and_test_list_the_file_they_place,
    )

def _the_writer_and_test_list_the_file_they_place(env, targets):
    placed = "%s/%s.gdbuild" % (_PACKAGE, _CHECKED_IN)
    for subject, target, test in [("writer", targets.writer, False), ("test", targets.test, True)]:
        manifest = manifest_content(target, ".run.json")
        env.expect.where(target = subject, field = "test").that_bool(manifest["test"]).equals(test)
        env.expect.where(target = subject, field = "writer").that_str(manifest["writer"]).equals(
            str(targets.writer.label),
        )
        env.expect.where(target = subject, field = "built").that_str(manifest["built"]).equals(
            "%s/%s.gdbuild" % (_PACKAGE, targets.derived.label.name),
        )
        env.expect.where(target = subject, field = "checked_in").that_str(manifest["checked_in"]).equals(placed)
        env.expect.where(target = subject, field = "target").that_str(manifest["target"]).equals(placed)

# A file nobody checked in yet is listed without its checked-in copy; the test fails for it
# and names the writer.
def _test_a_missing_checked_in_file_is_listed_empty(name):
    analysis_test(
        name = name,
        targets = _profile(name),
        impl = _a_missing_checked_in_file_is_listed_empty,
    )

def _a_missing_checked_in_file_is_listed_empty(env, targets):
    manifest = manifest_content(targets.test, ".run.json")
    env.expect.that_str(manifest["checked_in"]).equals("")

def _test_the_profile_size_and_timeout_reach_the_test(name):
    analysis_test(
        name = name,
        targets = _profile(name, size = "small", timeout = "short"),
        impl = _the_profile_size_and_timeout_reach_the_test,
    )

def _the_profile_size_and_timeout_reach_the_test(env, targets):
    test = env.expect.that_target(targets.test)
    test.attr("size", factory = subjects.str).equals("small")
    test.attr("timeout", factory = subjects.str).equals("short")

def runtime_profile_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_a_missing_checked_in_file_is_listed_empty,
            _test_the_profile_size_and_timeout_reach_the_test,
            _test_the_derivation_runs_the_editor_over_the_view,
            _test_the_engine_selects_the_editor,
            _test_the_keep_list_joins_the_ruleset_list_and_the_targets,
            _test_the_writer_and_test_list_the_file_they_place,
        ],
    )
