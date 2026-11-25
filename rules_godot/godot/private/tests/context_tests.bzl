"""
The project context: which imports resources declare outside and under it, where native code
is configured, and what a project itself depends on.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot:defs.bzl", "godot_project")
load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/private:paths.bzl", "mapped_path")
load("//godot/private:providers.bzl", "GodotExtensionInfo", "GodotProjectInfo", "GodotResourcesInfo")
load("//godot/private:view.bzl", "GodotViewInfo")
load(":action_inputs.bzl", "godot_actions", "import_manifests", "source_inputs")
load(":manifests.bzl", "manifest_content", "written_file")
load(":views.bzl", "run_view")

_FIXTURE = "//godot/private/tests/fixtures/project_with_shared_unit"
_PROJECT_SETTING = str(Label("//godot/private:project"))

def _under(project):
    return {_PROJECT_SETTING: str(Label(project))}

# FR-009: building resources outside every operation declares no import, theirs or their
# dependencies'.
def _test_resources_outside_an_operation_import_nothing(name):
    analysis_test(
        name = name,
        target = _FIXTURE + ":home",
        impl = _resources_outside_an_operation_import_nothing,
        extra_target_under_test_aspects = [godot_actions],
    )

def _resources_outside_an_operation_import_nothing(env, target):
    env.expect.that_collection(target[GodotResourcesInfo].imports.to_list(), expr = "imports").contains_exactly([])
    for unit in ["base", "home", "home_buffer"]:
        env.expect.where(unit = unit).that_collection(import_manifests(target, unit)).has_size(0)

# FR-008, FR-009: under a context a unit declares one import, under the context's import
# configuration, after the imports of its dependencies; it stages its own importable files,
# while the manifests of its dependencies and import inputs list theirs. Import inputs are
# staged as they are, not imported for it. Its own scripts
# and scenes are no input: a unit with only those stages nothing of its own.
def _test_import_reads_own_files_import_inputs_and_dependency_imports(name):
    analysis_test(
        name = name,
        targets = {
            "base": _FIXTURE + ":base",
            "home": _FIXTURE + ":home",
            "home_buffer": _FIXTURE + ":home_buffer",
            "main": _FIXTURE + ":main",
            "project": _FIXTURE,
        },
        impl = _import_reads_own_files_import_inputs_and_dependency_imports,
        extra_target_under_test_aspects = [godot_actions],
        config_settings = _under(_FIXTURE),
    )

def _import_reads_own_files_import_inputs_and_dependency_imports(env, targets):
    home = targets.home[GodotResourcesInfo]
    env.expect.that_collection(sorted([file.basename for file in home.imports.to_list()]), expr = "home imports").contains_exactly([
        "base.import",
        "home.import",
    ])
    manifests = import_manifests(targets.home, "home")
    env.expect.that_collection(manifests, expr = "home import manifests").has_size(1)
    configuration = targets.project[GodotProjectInfo].import_configuration
    for manifest in manifests.values():
        env.expect.that_str(manifest["project_file"]).equals(mapped_path(configuration))
        env.expect.that_collection(manifest["outputs"]).contains_exactly(["main/home.gd", "main/home.svg"])
    env.expect.that_dict(manifest_content(targets.home, ".resource_paths.json")).keys().contains_exactly(["main/home.svg"])
    env.expect.that_collection(
        home.resource_path_manifests.to_list(),
        expr = "staged manifests of home's import",
    ).contains_exactly([
        written_file(getattr(targets, unit), ".resource_paths.json")
        for unit in ["base", "home", "home_buffer"]
    ])

    # The autoload script and the main scene are main's only own files.
    env.expect.that_collection(import_manifests(targets.main, "main"), expr = "main import manifests").has_size(1)
    env.expect.that_bool(written_file(targets.main, ".resource_paths.json") == None, expr = "main stages own files").equals(True)

# FR-010: an extension reached from two contexts and from a pack's native path is configured
# once, in the configuration it has as a direct dependency.
def _test_extension_is_configured_once_across_contexts(name):
    analysis_test(
        name = name,
        targets = {
            "direct": _FIXTURE + ":hello",
            "first": run_view(name + "_first", _FIXTURE, [_FIXTURE + ":main"]),
            "pack": _FIXTURE + ":pack",
            "second": run_view(name + "_second", _FIXTURE + ":other_project", [_FIXTURE + ":main"]),
        },
        impl = _extension_is_configured_once_across_contexts,
    )

def _extension_files(extension):
    return [extension.runtime_descriptor.path] + ([extension.library.file.path] if extension.library else [])

def _extension_is_configured_once_across_contexts(env, targets):
    direct = _extension_files(targets.direct[GodotExtensionInfo])
    env.expect.that_collection(direct, expr = "the extension's descriptor and library").has_size(2)
    for subject, extensions in [
        ("first", targets.first[GodotViewInfo].export_extensions),
        ("second", targets.second[GodotViewInfo].export_extensions),
        ("pack", targets.pack[GodotPackInfo].project.export_extensions),
    ]:
        env.expect.where(reached_from = subject).that_collection(
            [path for extension in extensions for path in _extension_files(extension)],
        ).contains_exactly(direct)

# FR-002: a project reads its project file and nothing of the content: not the autoload
# script or the main scene it names, and its context files only through its operations.
def _test_project_reads_only_its_project_file(name):
    godot_project(
        name = name + "_project",
        autoloads = {"State": "*res://main/state.gd"},
        context_files = {_FIXTURE + ":main/icon.svg": "branding/icon.svg"},
        main_scene = "main/main.tscn",
        project_file = _FIXTURE + ":project.godot",
        tags = ["manual"],
    )
    analysis_test(name = name, target = name + "_project", impl = _project_reads_only_its_project_file)

def _project_reads_only_its_project_file(env, target):
    project = target[GodotProjectInfo]
    env.expect.that_collection(target[DefaultInfo].files.to_list(), expr = "default outputs").contains_exactly([])
    env.expect.that_collection(project.context_files.keys(), expr = "context files").contains_exactly(["branding/icon.svg"])
    fixture = Label(_FIXTURE).package + "/"
    read = source_inputs(target[TestingAspectInfo].actions, fixture)
    env.expect.that_collection(read, expr = "fixture files the project's actions read").contains_exactly([
        fixture + "project.godot",
    ])

def context_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_extension_is_configured_once_across_contexts,
            _test_import_reads_own_files_import_inputs_and_dependency_imports,
            _test_project_reads_only_its_project_file,
            _test_resources_outside_an_operation_import_nothing,
        ],
    )
