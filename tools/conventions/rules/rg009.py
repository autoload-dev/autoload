"""RG009: projects lie at the fixed places of their consumers."""

from collections.abc import Iterable

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.layout import RULESET_MODULE


class ProjectPlaces:
    info = RuleInfo(
        "RG009",
        "Projects lie at the fixed places of their consumers",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        configurations = workspace.godot_configurations
        for path in sorted(configurations):
            # The white-box fixtures of the ruleset module may live anywhere there.
            if workspace.owner(path.as_posix()) == RULESET_MODULE:
                continue
            if workspace.typed_directory(path) is not None:
                continue
            yield Finding(
                Location(path.as_posix(), 1),
                "Godot configurations must belong to a project at a fixed place of their consumer",
            )
        for project, members in workspace.typed_directories("projects").items():
            location = Location(members[0], 1)
            if not workspace.has_build(project):
                yield Finding(
                    location, f"application project must own a BUILD file: {project}"
                )
            if not any(config.is_relative_to(project) for config in configurations):
                yield Finding(
                    location,
                    f"application project must contain a Godot configuration: {project}",
                )
