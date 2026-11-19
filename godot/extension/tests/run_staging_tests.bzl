"""Runs stage what their editor loads; pack exports need no extension runtime library."""

load("@platforms//host:constraints.bzl", "HOST_CONSTRAINTS")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:providers.bzl", "GodotExtensionInfo")
load("//godot/private/tests:pack_actions.bzl", "PackActionsInfo", "pack_actions")
load("//godot/private/tests:pack_forms.bzl", "GODOT_EXPORT")

_EXTENSION_ATTRS = {"extension": attr.label(providers = [GodotExtensionInfo])}

def _editor_files(extension, resource_paths):
    return {file: True for path, file in resource_paths.items() if path != extension.descriptor_path}

# The actions that make a pack's PCK in either form: Godot's export, or the configuration
# export and the writer.
_MAKING = ["GodotPack", "GodotPackConfiguration", "GodotPackWrite"]

def _exports(target):
    """The pack's GodotPack actions, which the pack_actions aspect collects."""
    return [action for action in target[PackActionsInfo].actions if action.mnemonic == "GodotPack"]

def _making(target):
    """The actions that make the pack's PCK, in whichever form the build chooses."""
    return [action for action in target[PackActionsInfo].actions if action.mnemonic in _MAKING]

def _runtime_libraries(extension):
    return [extension.library.file] if extension.library else []

def _runfiles(target):
    return {file: True for file in target[DefaultInfo].default_runfiles.files.to_list()}

def _expect_staging(env, runfiles, extension):
    editor = _editor_files(extension, extension.editor_resource_paths)
    env.expect.that_bool(bool(editor), expr = "the fixture builds an extension editor library").equals(True)
    for file in editor:
        # It builds for the editor actions' execution platform, which need not be the
        # test's; it also shares the extension runtime library's runfiles path.
        env.expect.that_bool(file in runfiles, expr = "a run stages no extension editor library: " + file.path).equals(False)
    for file in _runtime_libraries(extension):
        env.expect.that_bool(file in runfiles, expr = "a run stages the extension runtime library: " + file.path).equals(True)

def _run_staging_test(name, run):
    analysis_test(
        name = name,
        target = run,
        impl = _run_stages_runtime_library_impl,
        attrs = _EXTENSION_ATTRS,
        attr_values = {"extension": "//godot/extension/tests/fixtures/c_abi:hello"},
    )

def _run_stages_runtime_library_impl(env, target):
    _expect_staging(env, _runfiles(target), env.ctx.attr.extension[GodotExtensionInfo])

def _own_configuration_test(name, run, config_settings = {}):
    """Expect the run to stage the extension libraries of its own configuration, which the aspect collects."""
    analysis_test(
        name = name,
        target = run,
        impl = _run_stages_runtime_library_of_its_configuration,
        extra_target_under_test_aspects = [_extensions],
        config_settings = config_settings,
    )

# A source run runs in the editor variant and stages that variant's library.
def _test_project_run_stages_runtime_library_only(name):
    _own_configuration_test(name, ":run_staging_project_run")

def _test_pack_run_stages_runtime_library_only(name):
    _run_staging_test(name, ":run_staging_pack_run")

_ExtensionsInfo = provider(doc = "Extensions a run's project contains, in its configuration.", fields = ["extensions"])

def _extensions_impl(target, ctx):
    found = [target[GodotExtensionInfo]] if GodotExtensionInfo in target else []
    for name in ["view", "deps"]:
        value = getattr(ctx.rule.attr, name, None)
        for dep in value if type(value) == "list" else [value] if value else []:
            if _ExtensionsInfo in dep:
                found.extend(dep[_ExtensionsInfo].extensions)
    return [_ExtensionsInfo(extensions = found)]

_extensions = aspect(implementation = _extensions_impl, attr_aspects = ["view", "deps"])

# bazel run for this host's own platform, whatever the build targets. The aspect takes
# the extensions from the run's own configuration.
def _test_host_platform_run_stages_runtime_library(name):
    _own_configuration_test(
        name,
        ":host_platform_run",
        {"//command_line_option:platforms": str(Label("@platforms//host"))},
    )

def _run_stages_runtime_library_of_its_configuration(env, target):
    extensions = target[_ExtensionsInfo].extensions
    env.expect.that_bool(bool(extensions), expr = "the run's project contains an extension").equals(True)
    for extension in extensions:
        _expect_staging(env, _runfiles(target), extension)

# A target platform the local host does not run: the other desktop operating system.
_OTHER = "remote_linux" if "@platforms//os:osx" in HOST_CONSTRAINTS else "remote_macos"

def _foreign_target_platform_run_test(name, run):
    analysis_test(
        name = name,
        target = run,
        impl = _foreign_target_platform_run_impl,
        attrs = _EXTENSION_ATTRS,
        attr_values = {"extension": ":cross_extension"},
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/engine/private/tests:" + _OTHER)),
        },
    )

def _foreign_target_platform_run_impl(env, target):
    staged = _runfiles(target)
    extension = env.ctx.attr.extension[GodotExtensionInfo]
    for file in _editor_files(extension, extension.host_editor_resource_paths):
        env.expect.that_bool(
            file in staged,
            expr = "bazel run for a foreign target platform stages the extension host editor library: " + file.path,
        ).equals(True)
    for file in _runtime_libraries(extension):
        env.expect.that_bool(
            file in staged,
            expr = "bazel run for a foreign target platform stages no extension runtime library: " + file.path,
        ).equals(False)

def _test_foreign_platform_project_run_stages_host_editor_library(name):
    _foreign_target_platform_run_test(name, ":foreign_target_platform_project_run")

def _test_foreign_platform_pack_run_stages_host_editor_library(name):
    _foreign_target_platform_run_test(name, ":foreign_target_platform_pack_run")

def _test_pack_export_needs_no_runtime_library(name):
    analysis_test(
        name = name,
        target = ":run_staging_pack",
        impl = _test_pack_export_needs_no_runtime_library_impl,
        attrs = _EXTENSION_ATTRS,
        attr_values = {"extension": "//godot/extension/tests/fixtures/c_abi:hello"},
        extra_target_under_test_aspects = [pack_actions],
    )

# In either form, the actions that make the PCK load the extension editor library and pack
# the runtime descriptor, and wait for no extension runtime library.
def _test_pack_export_needs_no_runtime_library_impl(env, target):
    making = _making(target)
    env.expect.that_bool(len(making) > 0, expr = "actions making the PCK").equals(True)
    inputs = {file: True for action in making for file in action.inputs.to_list()}
    extension = env.ctx.attr.extension[GodotExtensionInfo]
    for file in _runtime_libraries(extension):
        env.expect.that_bool(file in inputs, expr = "the export does not wait for the extension runtime library: " + file.path).equals(False)
    for file in extension.editor_resource_paths.values():
        env.expect.that_bool(file in inputs, expr = "the export's editor loads the extension editor library: " + file.path).equals(True)
    env.expect.that_bool(extension.runtime_descriptor in inputs, expr = "the pack receives the runtime descriptor").equals(True)

# Each platform slice configures the extension of its own; one without an extension editor
# library stages its runtime files for the export.
def _test_multi_platform_slice_pack_exports_once(name):
    analysis_test(
        name = name,
        target = ":multi_platform_slice_pack",
        impl = _test_multi_platform_slice_pack_exports_once_impl,
        extra_target_under_test_aspects = [pack_actions],
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/private/config/tests:android_distribution")),
        } | GODOT_EXPORT,
    )

def _test_multi_platform_slice_pack_exports_once_impl(env, target):
    env.expect.that_int(len(_exports(target)), expr = "GodotPack actions; the pack exports its platform slices once").equals(1)

    # The pack merges one descriptor fragment per platform slice into its descriptor.
    merges = [action for action in target[PackActionsInfo].actions if action.mnemonic == "GodotExtensionDescriptors"]
    env.expect.that_int(len(merges), expr = "GodotExtensionDescriptors actions").equals(1)
    fragments = [
        file
        for action in merges
        for file in action.inputs.to_list()
        if file.basename == "multi_platform_slice_extension.gdextension"
    ]
    env.expect.that_int(len(fragments), expr = "descriptor fragments, one per platform slice").equals(2)

def run_staging_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_project_run_stages_runtime_library_only,
            _test_pack_run_stages_runtime_library_only,
            _test_host_platform_run_stages_runtime_library,
            _test_foreign_platform_project_run_stages_host_editor_library,
            _test_foreign_platform_pack_run_stages_host_editor_library,
            _test_pack_export_needs_no_runtime_library,
            _test_multi_platform_slice_pack_exports_once,
        ],
    )
