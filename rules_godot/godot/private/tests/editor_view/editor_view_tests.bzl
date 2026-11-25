"""What a godot_editor target passes to the editor view runner in its manifest and runfiles."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot:defs.bzl", "godot_editor")
load("//godot/private:view.bzl", "GodotViewInfo")
load("//godot/private/tests:manifests.bzl", "manifest_content")

_FIXTURE = "//godot/private/tests/editor_view/fixtures/project_edited_in_the_view"
_PROJECT = _FIXTURE
_DEPS = [_FIXTURE + ":main", _FIXTURE + ":view_check"]

def _view(target):
    return manifest_content(target, ".run.json")

# The target is a launcher named after it that starts the runner with its manifest; the
# manifest names the target's own editor view and its view's editor configuration.
def _test_editor_view_launcher_and_manifest(name):
    godot_editor(name = name + "_edit", project = _PROJECT, tags = ["manual"], deps = _DEPS)
    analysis_test(
        name = name,
        targets = {"edit": name + "_edit", "view": name + "_edit.view"},
        impl = _editor_view_launcher_and_manifest,
    )

def _editor_view_launcher_and_manifest(env, targets):
    edit = targets.edit
    project = targets.view[GodotViewInfo]
    executable = edit[DefaultInfo].files_to_run.executable
    env.expect.that_str(executable.basename).equals(edit.label.name)
    launchers = [action for action in edit[TestingAspectInfo].actions if action.mnemonic == "TemplateExpand"]
    env.expect.that_collection([action.outputs.to_list() for action in launchers], expr = "launcher outputs").contains_exactly([[executable]])
    env.expect.that_str(launchers[0].substitutions["{MANIFEST}"]).equals(
        "_main/godot/private/tests/editor_view/%s.run.json" % edit.label.name,
    )
    manifest = _view(edit)
    env.expect.where(field = "view").that_str(manifest["view"]).equals(
        ".godot-editor/godot/private/tests/editor_view/" + edit.label.name,
    )
    env.expect.where(field = "label").that_str(manifest["label"]).equals(str(edit.label))
    env.expect.where(field = "project_file").that_str(manifest["project_file"]).equals(
        project.editor_project_file.short_path,
    )
    env.expect.where(field = "metadata").that_str(manifest["metadata"]).equals(project.metadata.short_path)
    env.expect.where(field = "composed_settings").that_dict(manifest["composed_settings"]).contains_exactly(
        project.composed_settings,
    )
    env.expect.that_collection(
        edit[DefaultInfo].default_runfiles.files.to_list(),
        expr = "runfiles",
    ).contains_at_least([project.editor_project_file, project.metadata])

def _test_editor_env_reaches_manifest(name):
    godot_editor(name = name + "_edit", env = {"EDITOR_THEME": "light"}, project = _PROJECT, tags = ["manual"], deps = _DEPS)
    analysis_test(name = name, target = name + "_edit", impl = _editor_env_reaches_manifest)

def _editor_env_reaches_manifest(env, target):
    env.expect.where(field = "env").that_dict(_view(target)["env"]).contains_exactly({"EDITOR_THEME": "light"})

def _test_write_sidecars_reaches_manifest(name):
    godot_editor(name = name + "_default", project = _PROJECT, tags = ["manual"], deps = _DEPS)
    godot_editor(name = name + "_without", project = _PROJECT, tags = ["manual"], write_sidecars = False, deps = _DEPS)
    analysis_test(
        name = name,
        targets = {"default": name + "_default", "without": name + "_without"},
        impl = _write_sidecars_reaches_manifest,
    )

def _write_sidecars_reaches_manifest(env, targets):
    env.expect.where(target = "default").that_bool(_view(targets.default)["write_sidecars"]).equals(True)
    env.expect.where(target = "without").that_bool(_view(targets.without)["write_sidecars"]).equals(False)

def editor_view_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_editor_env_reaches_manifest,
            _test_editor_view_launcher_and_manifest,
            _test_write_sidecars_reaches_manifest,
        ],
    )
