"""
Where an authored sidecar must be declared: in the resources that declare its source, not
by another dependency, a dependent or an import input that adds it later. A file Godot
ignores comes with the .gdignore or project.godot that hides its directory the same way.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:defs.bzl", "godot_project", "godot_resources")
load("//godot/private:view.bzl", "GodotViewInfo")
load(":expected_failures.bzl", "failure_test")
load(":views.bzl", "run_view")

visibility("private")

_FIXTURE = "//godot/private/tests/fixtures/import_context"
_PROJECT_FILE = _FIXTURE + ":project.godot"
_HELPER_UID = _FIXTURE + "/main/shared:helper.gd.uid"

# The failure names the target that declares the source; `*` stands for its package.
_LATE_UID = "Authored sidecar res://main/main.gd.uid must be declared in *:resource_without_sidecars with res://main/main.gd"

def _project(name):
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    return name + "_project"

# An operation rejects a sidecar that one of its dependencies adds to another's source.
def _test_project_rejects_uid_sidecar_of_another_dependency(name):
    view = run_view(name + "_run", _project(name), [
        _FIXTURE + ":resource_without_sidecars",
        _FIXTURE + ":uid_sidecar",
    ])
    failure_test(name, view, _LATE_UID)

def _test_project_rejects_import_sidecar_of_another_dependency(name):
    view = run_view(name + "_run", _project(name), [
        _FIXTURE + ":resource_without_sidecars",
        _FIXTURE + ":textures",
    ])
    failure_test(
        name,
        view,
        "Authored sidecar res://main/icon.svg.import must be declared in *:resource_without_sidecars with res://main/icon.svg",
    )

def _test_dependent_rejects_its_own_late_sidecar(name):
    godot_resources(
        name = name + "_resources",
        resource_paths = {_HELPER_UID: "main/main.gd.uid"},
        tags = ["manual"],
        deps = [_FIXTURE + ":resource_without_sidecars"],
    )
    failure_test(name, name + "_resources", _LATE_UID)

# A sidecar from another dependency arrives just as late.
def _test_resources_reject_sidecar_of_a_sibling_dependency(name):
    godot_resources(
        name = name + "_resources",
        tags = ["manual"],
        deps = [
            _FIXTURE + ":resource_without_sidecars",
            _FIXTURE + ":uid_sidecar",
        ],
    )
    failure_test(name, name + "_resources", _LATE_UID)

def _test_resources_reject_sidecar_of_an_import_input(name):
    godot_resources(
        name = name + "_resources",
        import_inputs = [_FIXTURE + ":uid_sidecar"],
        tags = ["manual"],
        deps = [_FIXTURE + ":resource_without_sidecars"],
    )
    failure_test(name, name + "_resources", _LATE_UID)

# Sidecars declared with their sources become members of an operation.
def _test_project_accepts_sidecars_declared_with_their_sources(name):
    analysis_test(
        name = name,
        target = run_view(name + "_run", _project(name), [_FIXTURE + ":resource_with_sidecars"]),
        impl = _project_accepts_sidecars_declared_with_their_sources,
    )

def _project_accepts_sidecars_declared_with_their_sources(env, target):
    env.expect.that_collection(sorted(target[GodotViewInfo].member_resource_paths), expr = "member resource paths").contains_exactly([
        "main/icon.svg",
        "main/icon.svg.import",
        "main/main.gd",
        "main/main.gd.uid",
    ]).in_order()

# Import inputs may bring a source and its sidecar together.
def _test_import_inputs_may_bring_a_source_and_its_sidecar(name):
    analysis_test(name = name, target = _FIXTURE + ":sidecar_import_inputs", impl = _analyzes)

def _analyzes(_env, _target):
    """The claim is that analysis succeeds; analysis_test fails the test otherwise."""
    pass

_IGNORED_FIXTURE = "//godot/private/tests/godot_ignored/fixtures/project_with_ignored_directory"

# A file below a .gdignore that another target declares fails like a sidecar declared
# apart from its source.
def _test_resources_reject_ignored_file_apart_from_its_gdignore(name):
    failure_test(
        name,
        _IGNORED_FIXTURE + ":template_without_its_ignore_file",
        "res://report/template.html is in a directory Godot ignores; declare it in *:ignore_file with res://report/.gdignore, or move it out of that directory",
    )

# An add-on's part holds the marker of the directories its files are in.
def _test_addon_rejects_ignored_file_apart_from_its_gdignore(name):
    failure_test(
        name,
        _IGNORED_FIXTURE + ":addon_split_at_ignored_directory",
        "*: res://addons/split/report/template.html is in a directory Godot ignores; it belongs in editor_srcs with res://addons/split/report/.gdignore",
    )

def sidecar_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_dependent_rejects_its_own_late_sidecar,
            _test_import_inputs_may_bring_a_source_and_its_sidecar,
            _test_project_accepts_sidecars_declared_with_their_sources,
            _test_project_rejects_import_sidecar_of_another_dependency,
            _test_project_rejects_uid_sidecar_of_another_dependency,
            _test_resources_reject_sidecar_of_a_sibling_dependency,
            _test_resources_reject_sidecar_of_an_import_input,
            _test_resources_reject_ignored_file_apart_from_its_gdignore,
            _test_addon_rejects_ignored_file_apart_from_its_gdignore,
        ],
    )
