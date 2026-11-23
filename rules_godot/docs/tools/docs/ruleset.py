"""The ruleset's Bazel module name, for the checks that read its labels."""

MODULE = "autoload_rules_godot"


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
