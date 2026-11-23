"""Keep a Python launcher's import policy out of the Bazel the conventions check runs."""

from collections.abc import Mapping


def nested_tool_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """
    Copy caller variables for a nested Bazel. rules_python enables safe-path mode for its own
    launcher; passing it through changes the imports of other repositories' Python scripts.
    The ruleset's documentation module uses it for its checks' nested Bazel too.
    """
    return {
        name: value for name, value in environment.items() if name != "PYTHONSAFEPATH"
    }
