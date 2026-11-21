"""Test rules that build and run a target with one engine's toolchains."""

load("//godot/private:execution.bzl", "TEST_EXEC_GROUPS")

visibility("private")

_ENGINE = str(Label("//godot:engine"))

# The toolchain hubs of the root module's development engines, which MODULE.bazel registers.
ENGINES = {
    "beta": "@godot_beta//toolchains:all",
    "stable": "@godot//toolchains:all",
}

# The engine name that selects each hub: the stable engine is the default one.
_ENGINE_NAMES = {
    "beta": "beta",
    "stable": "",
}

def _engine_transition_impl(_settings, attr):
    # A build setting, unlike --extra_toolchains, stays out of the exec configuration, so
    # the tools of every engine's test share one.
    return {_ENGINE: _ENGINE_NAMES[attr.engine]}

_engine_transition = transition(
    implementation = _engine_transition_impl,
    inputs = [],
    outputs = [_ENGINE],
)

_ENGINE_ATTR = attr.string(mandatory = True, values = ENGINES.keys())

def _with_engine_impl(ctx):
    return [DefaultInfo(files = ctx.attr.target[0][DefaultInfo].files)]

with_engine = rule(
    doc = "The target built with the engine's toolchains, for analysis tests of its actions.",
    implementation = _with_engine_impl,
    attrs = {
        "engine": _ENGINE_ATTR,
        "target": attr.label(mandatory = True, cfg = _engine_transition),
    },
)

def _engine_test_impl(ctx):
    test = ctx.attr.test[0][DefaultInfo]
    executable = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(
        output = executable,
        target_file = test.files_to_run.executable,
        is_executable = True,
    )
    runfiles = ctx.runfiles([executable]).merge(test.default_runfiles)
    return [DefaultInfo(executable = executable, runfiles = runfiles)]

engine_test = rule(
    doc = "Run a test target built with the engine's toolchains.",
    implementation = _engine_test_impl,
    attrs = {
        "engine": _ENGINE_ATTR,
        "test": attr.label(mandatory = True, executable = True, cfg = _engine_transition),
    },
    test = True,
    # The test action runs on an execution platform with an editor, as godot_test's does.
    exec_groups = TEST_EXEC_GROUPS,
)
