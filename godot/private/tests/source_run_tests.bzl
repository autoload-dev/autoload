"""
What godot_run and godot_test pass to the runner in their run manifest and runfiles, and
which combinations of what they run they reject.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:defs.bzl", "godot_project", "godot_run", "godot_test")
load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/private:run.bzl", "validate_run_sources")
load(":expected_failures.bzl", "failure_test")
load(":manifests.bzl", "manifest_content")
load(":mocks.bzl", "mocks")

_FIXTURE = "//godot/private/tests/fixtures/import_context"
_PROJECT = _FIXTURE + ":configured_project"

# The resources holding the configured project's main scene, which a run needs.
_DEPS = [_FIXTURE + ":configured_check", _FIXTURE + ":configured_resources"]
_PACKS = "//godot/private/tests/fixtures/project_with_pack_membership"

def _run(target):
    return manifest_content(target, ".run.json")

def _runfiles(target):
    return target[DefaultInfo].default_runfiles.files.to_list()

# Each additional pack reaches the working directory under its file name.
def _test_additional_packs_reach_manifest_and_runfiles(name):
    godot_run(
        name = name + "_run",
        additional_packs = {
            _PACKS + ":dlc_pack": "dlc.pck",
            _PACKS + ":red_pack": "red.pck",
        },
        project = _PROJECT,
        tags = ["manual"],
        deps = _DEPS,
    )
    analysis_test(
        name = name,
        targets = {"dlc": _PACKS + ":dlc_pack", "red": _PACKS + ":red_pack", "run": name + "_run"},
        impl = _additional_packs_reach_manifest_and_runfiles,
    )

def _additional_packs_reach_manifest_and_runfiles(env, targets):
    dlc = targets.dlc[GodotPackInfo].pack_file
    red = targets.red[GodotPackInfo].pack_file
    env.expect.where(field = "additional_packs").that_dict(
        _run(targets.run)["additional_packs"],
    ).contains_exactly({"dlc.pck": dlc.short_path, "red.pck": red.short_path})
    env.expect.that_collection(_runfiles(targets.run), expr = "runfiles").contains_at_least([dlc, red])

def _test_additional_packs_sharing_a_file_name_fail(name):
    godot_run(
        name = name + "_run",
        additional_packs = {
            _PACKS + ":dlc_pack": "dlc.pck",
            _PACKS + ":red_pack": "dlc.pck",
        },
        project = _PROJECT,
        tags = ["manual"],
        deps = _DEPS,
    )
    failure_test(name, name + "_run", 'Additional packs * and * share the file name "dlc.pck"')

def _test_headless_attribute_reaches_manifest(name):
    godot_run(name = name + "_run", headless = False, project = _PROJECT, tags = ["manual"], deps = _DEPS)
    analysis_test(name = name, target = name + "_run", impl = _runs_with_display)

def _runs_with_display(env, target):
    env.expect.where(field = "headless").that_bool(_run(target)["headless"]).equals(False)

# godot_run and godot_test each follow the flag when headless is unset.
def _test_unset_headless_follows_flag(name):
    godot_run(name = name + "_run", project = _PROJECT, tags = ["manual"], deps = _DEPS)
    godot_test(name = name + "_test", project = _PROJECT, tags = ["manual"])
    analysis_test(
        name = name,
        targets = {"run": name + "_run", "test": name + "_test"},
        impl = _unset_headless_follows_flag,
        config_settings = {str(Label("//godot:headless")): False},
    )

def _unset_headless_follows_flag(env, targets):
    for subject, target in [("run", targets.run), ("test", targets.test)]:
        env.expect.where(subject = subject, field = "headless").that_bool(
            _run(target)["headless"],
        ).equals(False)

def _test_env_reaches_manifest(name):
    godot_run(name = name + "_run", env = {"GAME_MODE": "demo"}, project = _PROJECT, tags = ["manual"], deps = _DEPS)
    analysis_test(name = name, target = name + "_run", impl = _env_reaches_manifest)

def _env_reaches_manifest(env, target):
    env.expect.where(field = "env").that_dict(_run(target)["env"]).contains_exactly({"GAME_MODE": "demo"})

def _test_data_reaches_runfiles(name):
    godot_run(
        name = name + "_run",
        data = [_FIXTURE + ":main/importer_data.txt"],
        project = _PROJECT,
        tags = ["manual"],
        deps = _DEPS,
    )
    analysis_test(name = name, target = name + "_run", impl = _data_reaches_runfiles)

def _data_reaches_runfiles(env, target):
    env.expect.that_collection(
        [file.short_path for file in _runfiles(target)],
        expr = "runfiles",
    ).contains("godot/private/tests/fixtures/import_context/main/importer_data.txt")

# A run fails on reported errors unless it only reports them.
def _test_run_engine_errors_reach_its_manifest(name):
    godot_project(
        name = name + "_project",
        project_file = _FIXTURE + ":project.godot",
        tags = ["manual"],
    )
    godot_run(
        name = name + "_run",
        engine_errors = "report",
        project = name + "_project",
        tags = ["manual"],
    )
    godot_run(
        name = name + "_default",
        project = name + "_project",
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        targets = {"default": name + "_default", "report": name + "_run"},
        impl = _run_engine_errors_reach_its_manifest,
    )

def _run_engine_errors_reach_its_manifest(env, targets):
    for subject, target, expected in [("default", targets.default, "fail"), ("report", targets.report, "report")]:
        env.expect.where(run = subject).that_str(_run(target)["engine_errors"]).equals(expected)

# A run is a project with deps or a pack, never both.
def _test_project_and_pack_together_fail(env):
    errors, fail_ = mocks.errors()
    validate_run_sources("game", [":main"], None, ":pack", _fail = fail_)
    validate_run_sources("game", [], ":project", ":pack", _fail = fail_)
    validate_run_sources("game", [":main"], ":project", None, _fail = fail_)
    validate_run_sources("game", [], None, ":pack", _fail = fail_)
    env.expect.that_collection(errors).contains_exactly([
        "game: specify a project and deps, or a pack",
        "game: specify a project and deps, or a pack",
    ])

def source_run_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_additional_packs_reach_manifest_and_runfiles,
            _test_additional_packs_sharing_a_file_name_fail,
            _test_data_reaches_runfiles,
            _test_env_reaches_manifest,
            _test_headless_attribute_reaches_manifest,
            _test_run_engine_errors_reach_its_manifest,
            _test_unset_headless_follows_flag,
        ],
        basic_tests = [
            _test_project_and_pack_together_fail,
        ],
    )
