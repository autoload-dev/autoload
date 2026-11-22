"""The ruleset's Bazel module name, for tools that read or write its labels."""

MODULE = "autoload_rules_godot"
# The apparent repository a consumer module writes, as in @autoload_rules_godot//godot.
REPO = "@" + MODULE


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
