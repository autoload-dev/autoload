"""Exec groups of the rules that run the editor outside build actions."""

load("@platforms//host:constraints.bzl", "HOST_CONSTRAINTS")

visibility(["//godot/..."])

EDITOR_TOOLCHAIN = "//godot:editor_toolchain_type"

# The execution group of a bazel run with the toolchains its runner needs. bazel run starts
# binaries on the host, whatever executes the build's actions, so the runner and, with
# EDITOR_TOOLCHAIN, the editor resolve for an execution platform matching the host.
def _run_groups(toolchains):
    return {"run": exec_group(exec_compatible_with = HOST_CONSTRAINTS, toolchains = toolchains)}

# The execution group of a test with the toolchains its runner needs. Tests run on the
# execution platform of their test action; their editor follows Bazel's test exec group,
# which keeps its default test toolchain so the test stays on an execution platform it can
# run on.
def _test_groups(toolchains):
    return {"test": exec_group(toolchains = toolchains + [
        config_common.toolchain_type("@bazel_tools//tools/test:default_test_toolchain_type", mandatory = False),
    ])}

RUN_EXEC_GROUPS = _run_groups([EDITOR_TOOLCHAIN])

TEST_EXEC_GROUPS = _test_groups([EDITOR_TOOLCHAIN])

# For runners that start no editor.
EDITORLESS_RUN_EXEC_GROUPS = _run_groups([])

EDITORLESS_TEST_EXEC_GROUPS = _test_groups([])

def exec_group_editor(ctx, group):
    """
    Return the editor toolchain of an exec group.

    Args:
        ctx: Rule context of a rule declaring RUN_EXEC_GROUPS or TEST_EXEC_GROUPS.
        group: run or test.

    Returns:
        The editor's ToolchainInfo.godot struct.
    """
    return ctx.exec_groups[group].toolchains[EDITOR_TOOLCHAIN].godot
