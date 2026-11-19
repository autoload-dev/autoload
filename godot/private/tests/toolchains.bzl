"""Analysis-test settings that register their own toolchains independently of the caller."""

visibility([
    "//godot/engine/private/tests/...",
    "//godot/extension/tests/...",
    "//godot/platforms/private/tests/...",
    "//godot/private/config/tests/...",
    "//godot/private/tests/...",
])

_TOOLCHAINS = "//command_line_option:extra_toolchains"
_EXECUTION_PLATFORMS = "//command_line_option:extra_execution_platforms"

def own_toolchains(toolchains, execution_platforms = None):
    """
    Return config_settings that replace the caller's extra toolchains and execution platforms.

    Setting extra_toolchains replaces the command line's list, including the C++ toolchains
    of a remote execution platform such as BuildBuddy's, while that platform would stay an
    execution platform for the tools the test analyzes. The test therefore names its
    execution platforms too.

    Args:
        toolchains: Labels of the toolchains or registration sets the test registers.
            Strings resolve in rules_godot; another repository passes Label objects.
        execution_platforms: Labels of the execution platforms; the host by default.

    Returns:
        A dict to merge into an analysistest's config_settings.
    """
    return {
        _TOOLCHAINS: [str(Label(toolchain)) for toolchain in toolchains],
        _EXECUTION_PLATFORMS: [
            str(Label(platform))
            for platform in (execution_platforms or ["@platforms//host"])
        ],
    }
