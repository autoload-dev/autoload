"""A test rule that runs a test target with one development engine."""

load("//godot/private:execution.bzl", "TEST_EXEC_GROUPS")
load("//godot/private/tests:toolchains.bzl", "DEVELOPMENT_ENGINES", "ENGINE", "development_engine")

visibility("private")

def _engine_transition_impl(_settings, attr):
    return development_engine(attr.engine)

_engine_transition = transition(
    implementation = _engine_transition_impl,
    inputs = [],
    outputs = [ENGINE],
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
    doc = "Run a test target built with one development engine.",
    implementation = _engine_test_impl,
    attrs = {
        "engine": attr.string(
            doc = "The development engine, a key of DEVELOPMENT_ENGINES.",
            mandatory = True,
            values = DEVELOPMENT_ENGINES.keys(),
        ),
        "test": attr.label(mandatory = True, executable = True, cfg = _engine_transition),
    },
    test = True,
    # The test action runs on an execution platform with an editor, as godot_test's does.
    exec_groups = TEST_EXEC_GROUPS,
)
