"""Exec groups of the rules that run the editor outside build actions."""

load("@platforms//host:constraints.bzl", "HOST_CONSTRAINTS")

visibility(["//godot/..."])

EDITOR_TOOLCHAIN = "//godot:editor_toolchain_type"

# bazel run starts binaries on the host, whatever executes the build's actions, so their
# editor and runner resolve for an execution platform matching the host.
RUN_EXEC_GROUPS = {
    "run": exec_group(exec_compatible_with = HOST_CONSTRAINTS, toolchains = [EDITOR_TOOLCHAIN]),
}

# Tests run on the execution platform of their test action; their editor follows Bazel's
# test exec group, which keeps its default test toolchain so the test stays on an
# execution platform it can run on.
TEST_EXEC_GROUPS = {"test": exec_group(toolchains = [
    EDITOR_TOOLCHAIN,
    config_common.toolchain_type("@bazel_tools//tools/test:default_test_toolchain_type", mandatory = False),
])}

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
