"""The ruleset's Bazel module, for the checks that read its labels and run Bazel in it."""

from pathlib import Path

MODULE = "autoload_rules_godot"
# The API inventory, below the repository root: every Starlark module's API role.
INVENTORY = Path("tools/docs/api/modules.bzl")


def strip_repo(label: str) -> str:
    """Drop the ruleset's apparent or canonical repository from a label."""
    repository, separator, rest = label.partition("//")
    if (
        separator
        and repository.startswith("@")
        and repository.lstrip("@").removesuffix("+") == MODULE
    ):
        return "//" + rest
    return label
