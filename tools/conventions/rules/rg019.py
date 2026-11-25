"""RG019: a package's Godot project is named like its directory."""

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo


class ProjectTargetNames:
    info = RuleInfo(
        "RG019",
        "A package's Godot project is named like its directory",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        configured = context.workspace.configured
        for build, names in sorted(projects(context).items()):
            package = Path(build).parent
            if package in configured and package.name not in names:
                yield Finding(
                    Location(build, 1),
                    f"name the project of {package.as_posix()} like its directory: "
                    f"{package.name}",
                )


def projects(context: Context) -> dict[str, set[str | None]]:
    """The names of the projects that each BUILD file declares."""
    names: dict[str, set[str | None]] = defaultdict(set)
    for module in context.workspace.modules:
        for call in context.starlark.calls(module):
            if call.kind == "godot_project":
                names[call.location.path].add(call.literal_name)
    return names
