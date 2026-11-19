"""A test takes its execution platform's editor; bazel run takes the host's."""

load("@platforms//host:constraints.bzl", "HOST_CONSTRAINTS")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:execution.bzl", "RUN_EXEC_GROUPS", "TEST_EXEC_GROUPS", "exec_group_editor")

_Info = provider(doc = "Editors the exec groups resolve.", fields = ["run", "test"])

def _probe_impl(ctx):
    return [_Info(
        run = exec_group_editor(ctx, "run").provenance,
        test = exec_group_editor(ctx, "test").provenance,
    )]

# The exec groups of godot_run/godot_editor and godot_test, without the project graph
# whose build tools a stand-in execution platform cannot run.
_execution_probe = rule(
    implementation = _probe_impl,
    exec_groups = RUN_EXEC_GROUPS | TEST_EXEC_GROUPS,
)

# A stand-in remote execution platform never matches the host: it runs the other desktop
# operating system.
_HOST_OPERATING_SYSTEM = "macos" if "@platforms//os:osx" in HOST_CONSTRAINTS else "linux"
_REMOTE_OPERATING_SYSTEM = "linux" if _HOST_OPERATING_SYSTEM == "macos" else "macos"
_REMOTE_PLATFORM = "//godot/engine/private/tests:remote_" + _REMOTE_OPERATING_SYSTEM

def _test_test_and_run_take_their_execution_editors(name):
    _execution_probe(
        name = name + "_probe",
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = name + "_probe",
        impl = _test_test_and_run_take_their_execution_editors_impl,
        # The probe targets the remote operating system: a test runs on an execution platform
        # compatible with its target platform, while bazel run still runs on the host.
        config_settings = {
            "//command_line_option:platforms": str(Label(_REMOTE_PLATFORM)),
            "//command_line_option:extra_execution_platforms": [str(Label(_REMOTE_PLATFORM))],
            "//command_line_option:extra_toolchains": [
                str(Label("//godot/engine/private/tests/fixtures/remote_editors:all")),
            ],
        },
    )

def _test_test_and_run_take_their_execution_editors_impl(env, target):
    info = target[_Info]
    env.expect.where(
        claim = "a test runs the editor of its test action's execution platform",
    ).that_str(info.test.platform).equals(_REMOTE_OPERATING_SYSTEM)
    env.expect.that_str(Label(info.test.component).package.split("/")[-1]).equals("remote_editors")
    env.expect.where(
        claim = "bazel run starts the host's editor",
    ).that_str(info.run.platform).equals(_HOST_OPERATING_SYSTEM)

def execution_test_suite(name):
    test_suite(
        name = name,
        tests = [_test_test_and_run_take_their_execution_editors],
    )
