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
        workspace = context.workspace
        projects: dict[str, set[str | None]] = defaultdict(set)
        for module in workspace.modules:
            for call in context.starlark.calls(module):
                if call.kind == "godot_project":
                    projects[call.location.path].add(call.literal_name)
        for build, names in sorted(projects.items()):
            package = Path(build).parent
            if (package / "project.godot").as_posix() not in workspace.file_set:
                continue
            if package.name not in names:
                yield Finding(
                    Location(build, 1),
                    f"name the project of {package.as_posix()} like its directory: "
                    f"{package.name}",
                )
