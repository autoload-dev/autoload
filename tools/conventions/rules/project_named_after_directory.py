"""
project-named-after-directory: a package's Godot project is named like its directory.
"""

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo


def projects(context: Context) -> dict[str, set[str | None]]:
    """The names of the projects that each BUILD file declares."""
    names: dict[str, set[str | None]] = defaultdict(set)
    for module in context.workspace.modules:
        for call in context.starlark.calls(module):
            if call.kind == "godot_project":
                names[call.location.path].add(call.literal_name)
    return names


class ProjectTargetNames:
    info = RuleInfo(
        "project-named-after-directory",
        "A package's Godot project is named like its directory",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        configured = context.workspace.configured
        for build, names in sorted(projects(context).items()):
            package = Path(build).parent
            if package not in configured or package.name in names:
                continue
            if None in names:
                yield Finding(
                    Location(build, 1),
                    f"cannot read every project name of {package.as_posix()}",
                    "not_checked",
                )
            else:
                yield Finding(
                    Location(build, 1),
                    f"name the project of {package.as_posix()} like its directory: "
                    f"{package.name}",
                )
