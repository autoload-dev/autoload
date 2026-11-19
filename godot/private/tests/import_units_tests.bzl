"""
Which resources of a project become import units, and what their imports stage.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot:defs.bzl", "godot_project")
load("//godot:providers.bzl", "GodotResourcesInfo")
load("//godot/private:view.bzl", "GodotViewInfo")
load(":manifests.bzl", "written_content")
load(":views.bzl", "run_view")

_FIXTURE = "//godot/private/tests/fixtures/import_context"
_PROJECT_FILE = _FIXTURE + ":project.godot"

def _project(name):
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    return name + "_project"

# The project's one importer listing and one import configuration serve every unit, and
# only targets with files of their own are units. Whether a unit runs GodotImport is
# decided at execution from the importer listing.
def _test_only_resources_with_own_files_are_import_units(name):
    project = _project(name)
    analysis_test(
        name = name,
        targets = {
            "project": project,
            "view": run_view(name + "_run", project, [
                _FIXTURE + ":configured_check",
                _FIXTURE + ":transitive_consumer",
            ]),
        },
        impl = _only_resources_with_own_files_are_import_units,
    )

def _only_resources_with_own_files_are_import_units(env, targets):
    mnemonics = [action.mnemonic for action in targets.project[TestingAspectInfo].actions]
    for mnemonic in ["GodotImportableSuffixes", "GodotImportConfig"]:
        env.expect.that_int(len([m for m in mnemonics if m == mnemonic]), expr = mnemonic + " actions").equals(1)
    import_results = [result.short_path.rpartition("/")[2] for result in targets.view[GodotViewInfo].imports.to_list()]
    env.expect.that_collection(sorted(import_results), expr = "import results").contains_exactly([
        "configuration.runtime.import",
        "configured_check.import",
        "configured_resources.import",
        "transitive_consumer.import",
    ]).in_order()

# A target whose name is the last component of another unit's package gets an import output
# that does not contain the other unit's output.
def _test_import_units_of_nested_names_do_not_nest(name):
    view = run_view(name + "_run", _project(name), [
        _FIXTURE + ":textures",
        _FIXTURE + "/textures:icons",
    ])
    analysis_test(name = name, target = view, impl = _import_units_of_nested_names_do_not_nest)

def _import_units_of_nested_names_do_not_nest(env, target):
    project = target[GodotViewInfo]
    owners = [Label(owner) for owner in {owner: True for owner in project.member_owners.values()}]
    env.expect.that_bool(
        any([
            child.repo_name == parent.repo_name and child.package == parent.package + "/" + parent.name
            for parent in owners
            for child in owners
        ]),
        expr = "the fixture keeps the parent target / child package naming collision",
    ).equals(True)
    import_results = sorted([result.short_path for result in project.imports.to_list()])
    env.expect.that_collection(import_results, expr = "import results").has_size(2)
    for import_result in import_results:
        for other in import_results:
            env.expect.that_bool(
                other != import_result and other.startswith(import_result + "/"),
                expr = "%s contains %s" % (import_result, other),
            ).equals(False)

# Resources with files of their own stand for their own unit; without, for the units their
# dependencies stand for, and for none when those have no files either.
def _test_unit_heads_name_own_unit_or_dependency_heads(name):
    analysis_test(
        name = name,
        targets = {
            "combined": _FIXTURE + ":combined",
            "content": _FIXTURE + ":content",
            "extension_resources": _FIXTURE + ":extension_resources",
        },
        impl = _unit_heads_name_own_unit_or_dependency_heads,
    )

def _unit_heads_name_own_unit_or_dependency_heads(env, targets):
    content = str(Label(_FIXTURE + ":content"))
    for subject, heads in [("content", [content]), ("combined", [content]), ("extension_resources", [])]:
        env.expect.where(subject = subject, field = "unit_heads").that_collection(
            getattr(targets, subject)[GodotResourcesInfo].unit_heads,
        ).contains_exactly(heads)

# An import stages the unit's assets and its import inputs, scripts included; the unit's
# own scripts are no input, so editing them reruns no import.
def _test_scripts_reach_imports_only_as_import_inputs(name):
    project = _project(name)
    analysis_test(
        name = name,
        target = _FIXTURE + ":scripted_import",
        impl = _scripts_reach_imports_only_as_import_inputs,
        config_settings = {str(Label("//godot/private:project")): str(native.package_relative_label(project))},
    )

def _scripts_reach_imports_only_as_import_inputs(env, target):
    own = json.decode(written_content(target, ".resource_paths.json"))
    env.expect.that_collection(sorted(own), expr = "own staged paths").contains_exactly(["scripted/icon.svg"])
    scripts = json.decode(written_content(target, ".import_scripts.json"))
    env.expect.that_collection(sorted(scripts), expr = "staged import scripts").contains_exactly(["private_import_input.gd"])

def import_units_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_import_units_of_nested_names_do_not_nest,
            _test_only_resources_with_own_files_are_import_units,
            _test_scripts_reach_imports_only_as_import_inputs,
            _test_unit_heads_name_own_unit_or_dependency_heads,
        ],
    )
