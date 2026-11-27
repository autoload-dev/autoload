"""
What an operation's view of its project names in GodotViewInfo: its project file of each
purpose, its composed configuration with the owner of each setting, the extension paths it
disables for each purpose and the files it derives.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:defs.bzl", "godot_project")
load("//godot/private:providers.bzl", "GodotExtensionInfo")
load("//godot/private:view.bzl", "GodotViewInfo")
load(":views.bzl", "run_view")

visibility("private")

_FIXTURE = "//godot/private/tests/fixtures/import_context"
_PROJECT_FILE = _FIXTURE + ":project.godot"
_CONFIGURED = [_FIXTURE + ":configured_check", _FIXTURE + ":configured_resources"]
_NATIVE = "//godot/private/tests/fixtures/project_with_native_extension"

def _configured_view(name):
    return run_view(name + "_run", _FIXTURE, _CONFIGURED)

# The view composes project.godot once per purpose, each named after the view; the authored
# file stays the declared source.
def _test_project_names_its_project_files(name):
    analysis_test(name = name, target = _configured_view(name), impl = _project_names_its_project_files)

def _project_names_its_project_files(env, target):
    project = target[GodotViewInfo]
    for field, basename in [
        ("export_project_file", target.label.name + ".export.project.godot"),
        ("editor_project_file", target.label.name + ".editor.project.godot"),
    ]:
        file = getattr(project, field)
        env.expect.where(field = field).that_str(file.basename).equals(basename)
        env.expect.where(field = field).that_str(str(file.owner)).equals(str(target.label))
    authored = project.project.authored_project_file
    env.expect.where(field = "authored_project_file").that_str(authored.short_path).equals(
        Label(_PROJECT_FILE).package + "/project.godot",
    )
    env.expect.where(field = "authored_project_file").that_bool(authored.is_source).equals(True)

# A setting a resource contributes names that resource, one the project sets names the
# project; the export configuration holds the resolved values its packs compare.
# resource_composition_tests.bzl asserts overrides and autoloads.
def _test_composed_configuration_names_owners(name):
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        settings = {"display/window/size/viewport_width": "640"},
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        targets = {"project": name + "_project", "view": run_view(name + "_run", name + "_project", _CONFIGURED)},
        impl = _composed_configuration_names_owners,
    )

def _composed_configuration_names_owners(env, targets):
    project = targets.view[GodotViewInfo]
    env.expect.where(field = "composed_settings").that_dict(project.composed_settings).contains_exactly({
        "application/config/name": str(Label(_FIXTURE + ":configuration")),
        "autoload/State": str(Label(_FIXTURE + ":configuration")),
        "display/window/size/viewport_width": str(targets.project.label),
    })
    configuration = project.export_configuration
    env.expect.where(field = "export_configuration").that_collection(sorted(configuration)).contains_exactly([
        "autoloads",
        "importer_plugins",
        "main_scene",
        "settings",
    ]).in_order()
    env.expect.where(field = "export_configuration settings").that_dict(configuration["settings"]).contains_exactly({
        "application/config/name": '"Resources"',
        "display/window/size/viewport_width": "640",
    })
    env.expect.where(field = "export_configuration main_scene").that_str(configuration["main_scene"]).equals("")
    env.expect.where(field = "export_configuration importer_plugins").that_collection(configuration["importer_plugins"]).contains_exactly([])

# The export loads the fixture's extension through its editor files, and the pack lists it
# for the runtime.
def _test_extension_reaches_exports_and_the_runtime(name):
    analysis_test(
        name = name,
        targets = {
            "view": run_view(name + "_run", _NATIVE, [_NATIVE + ":hello", _NATIVE + ":main"]),
            "extension": _NATIVE + ":hello",
        },
        impl = _extension_reaches_exports_and_the_runtime,
    )

def _descriptors(extensions):
    return [extension.runtime_descriptor.short_path for extension in extensions]

def _extension_reaches_exports_and_the_runtime(env, targets):
    extension = targets.extension[GodotExtensionInfo]
    view = targets.view[GodotViewInfo]
    env.expect.that_collection(sorted(extension.editor_resource_paths)).contains("native/hello.gdextension")
    for field in ["export_extensions", "runtime_extensions"]:
        env.expect.where(field = field).that_collection(
            _descriptors(getattr(view, field)),
        ).contains_exactly([extension.runtime_descriptor.short_path])

# The view declares its initialization, metadata listing and resource graph as its own
# outputs, named after it.
def _test_project_declares_derived_files(name):
    analysis_test(name = name, target = _configured_view(name), impl = _project_declares_derived_files)

def _project_declares_derived_files(env, target):
    project = target[GodotViewInfo]
    for suffix, field, directory in [
        (".initialized", "initialized", True),
        (".metadata.json", "metadata", False),
        (".graph.json", "graph", False),
        (".graph-manifest.jsonl", "graph_manifest", False),
    ]:
        basename = target.label.name + suffix
        file = getattr(project, field)
        env.expect.where(field = field).that_str(file.basename).equals(basename)
        env.expect.where(field = field).that_bool(file.is_directory).equals(directory)
        env.expect.where(field = field).that_str(str(file.owner)).equals(str(target.label))

def project_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_composed_configuration_names_owners,
            _test_extension_reaches_exports_and_the_runtime,
            _test_project_declares_derived_files,
            _test_project_names_its_project_files,
        ],
    )
