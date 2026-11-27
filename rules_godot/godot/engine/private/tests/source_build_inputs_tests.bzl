"""
An edit of a source-built engine's module reruns only the engine's own build.

The fixture app packages a runtime built from engine sources with the bazel_probe module,
while the registered prebuilt editor imports and exports. Its imports and its pack take the
engine only through the editor toolchain, so neither the module's sources nor anything the
engine's native build writes is an input of GodotImport or GodotPack. GodotImport is a
directory-mapping template that analysis does not list as an action; the test asserts the
editor toolchain files it stages instead.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private/tests:engines.bzl", "ResolvedInfo")
load("//godot/private/tests:pack_forms.bzl", "GODOT_EXPORT")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

visibility("private")

_FIXTURE = "//godot/engine/private/tests/fixtures/source_built_runtime"
_MODULE_SOURCE = "godot/engine/private/tests/fixtures/source_build/modules/bazel_probe/register_types.cpp"
_NATIVE = ["CppCompile", "CppLink"]

_ReachedActionsInfo = provider(
    doc = "Godot and native actions a target reaches through its dependencies and engine toolchains.",
    fields = {"actions": "depset of struct(owner, action)"},
)

def _dependencies(value):
    if type(value) == "list":
        return value
    if type(value) == "dict":
        return value.keys()
    return [value]

def _toolchain_actions(ctx):
    toolchains = [
        ctx.rule.toolchains[toolchain_type]
        for toolchain_type in ["//godot:editor_toolchain_type", "//godot:runtime_toolchain_type"]
        if toolchain_type in ctx.rule.toolchains
    ]
    return [
        toolchain[_ReachedActionsInfo].actions
        for toolchain in toolchains
        if toolchain and _ReachedActionsInfo in toolchain
    ]

def _reached_actions_impl(target, ctx):
    own = [
        struct(owner = target.label, action = action)
        for action in target.actions
        if action.mnemonic.startswith("Godot") or action.mnemonic in _NATIVE
    ]
    transitive = [
        dependency[_ReachedActionsInfo].actions
        for attribute in dir(ctx.rule.attr)
        for dependency in _dependencies(getattr(ctx.rule.attr, attribute))
        if type(dependency) == "Target" and _ReachedActionsInfo in dependency
    ]
    return [_ReachedActionsInfo(actions = depset(own, transitive = transitive + _toolchain_actions(ctx)))]

_reached_actions = aspect(
    implementation = _reached_actions_impl,
    attr_aspects = ["*"],
    toolchains_aspects = ["//godot:editor_toolchain_type", "//godot:runtime_toolchain_type"],
    doc = "Collect the Godot and native actions a target reaches, through its engine toolchains too.",
)

def _entries(target, mnemonics):
    return [entry for entry in target[_ReachedActionsInfo].actions.to_list() if entry.action.mnemonic in mnemonics]

def _paths(files):
    return {file.short_path: None for file in files}

def _test_engine_module_edit_reruns_engine_build_only(name):
    analysis_test(
        name = name,
        targets = {
            "app": _FIXTURE + ":app",
            "engines": "//godot/engine/private/tests:probe",
        },
        impl = _engine_module_edit_reruns_engine_build_only,
        extra_target_under_test_aspects = [_reached_actions],
        config_settings = own_toolchains([_FIXTURE + ":runtime_macos_arm64_release.toolchain"]) | GODOT_EXPORT,
        # The fixture's source-built runtime is a macOS arm64 one.
        attr_values = {"target_compatible_with": ["@platforms//os:macos", "@platforms//cpu:aarch64"]},
    )

def _expect_only_the_engine_compiles_the_module(env, targets, fixture):
    readers = [
        entry
        for entry in targets.app[_ReachedActionsInfo].actions.to_list()
        if _MODULE_SOURCE in _paths(entry.action.inputs.to_list())
    ]
    env.expect.that_collection([entry.action.mnemonic for entry in readers]).contains("CppCompile")
    for entry in readers:
        env.expect.where(owner = str(entry.owner)).that_str(entry.action.mnemonic).equals("CppCompile")
        env.expect.where(owner = str(entry.owner)).that_str(entry.owner.package).equals(fixture)

def _engine_build_outputs(env, targets, fixture):
    """Return what the engine's build writes, from the module's object to the runtime executable."""
    built = {}
    for entry in _entries(targets.app, _NATIVE):
        if entry.owner.package == fixture:
            built.update(_paths(entry.action.outputs.to_list()))
    env.expect.that_collection([path for path in built if path.endswith("/register_types.o")]).has_size(1)
    runtime = targets.engines[ResolvedInfo].runtime
    env.expect.that_str(runtime.provenance.component).equals(str(Label(_FIXTURE + ":runtime_macos_arm64_release")))
    built.update(_paths(runtime.files.to_list()))
    return sorted(built)

def _expect_no_pack_reads(env, targets, changed):
    packs = _entries(targets.app, ["GodotPack"])
    env.expect.that_int(len(packs)).is_greater_than(0)
    for entry in packs:
        inputs = _paths(entry.action.inputs.to_list())
        for path in changed:
            env.expect.where(mnemonic = "GodotPack", path = path).that_bool(path in inputs).equals(False)

def _engine_module_edit_reruns_engine_build_only(env, targets):
    fixture = Label(_FIXTURE + ":app").package

    # Only the engine's native build reads the module source. The pack reads neither that
    # source nor the build's outputs.
    _expect_only_the_engine_compiles_the_module(env, targets, fixture)
    changed = [_MODULE_SOURCE] + _engine_build_outputs(env, targets, fixture)
    _expect_no_pack_reads(env, targets, changed)

    # GodotImport stages the editor toolchain's executable and files, which hold none of it.
    editor = targets.engines[ResolvedInfo].editor
    staged = _paths([editor.editor.executable] + editor.files.to_list())
    for path in changed:
        env.expect.where(role = "editor", path = path).that_bool(path in staged).equals(False)

def source_build_inputs_test_suite(name):
    test_suite(
        name = name,
        tests = [_test_engine_module_edit_reruns_engine_build_only],
    )
