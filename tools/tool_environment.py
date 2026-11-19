"""Keep a Python launcher's import policy out of separately invoked Bazel tools."""

import os
from collections.abc import Mapping


def nested_tool_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Copy caller variables while restoring build-tool sibling imports."""
    result = dict(environment)
    # rules_python enables safe-path mode for its own launcher. Passing it through
    # nested Bazel changes the import behavior of unrelated repository rules'
    # Python scripts.
    result.pop("PYTHONSAFEPATH", None)
    return result


def start_build_tool() -> None:
    """
    Prepare a build tool that `bazel run` started.

    Paths on its command line resolve against the directory `bazel run` was invoked from,
    and every process it starts gets the nested tool environment.
    """
    os.chdir(os.environ.get("BUILD_WORKING_DIRECTORY", "."))
    for name in os.environ.keys() - nested_tool_environment(os.environ).keys():
        del os.environ[name]
