"""Test rules that build and run a target with one engine's toolchains."""

load("//godot/private:execution.bzl", "TEST_EXEC_GROUPS")

visibility("private")

_TOOLCHAINS = "//command_line_option:extra_toolchains"

# The toolchain hubs of the root module's development engines.
ENGINES = {
    "beta": "@godot_beta//toolchains:all",
    "stable": "@godot//toolchains:all",
}

def _engine_transition_impl(settings, attr):
    # Appended, so the command line's toolchains, such as a remote execution platform's
    # C++ toolchain, stay in place.
    return {_TOOLCHAINS: settings[_TOOLCHAINS] + [str(Label(ENGINES[attr.engine]))]}

_engine_transition = transition(
    implementation = _engine_transition_impl,
    inputs = [_TOOLCHAINS],
    outputs = [_TOOLCHAINS],
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
