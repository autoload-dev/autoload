"""RG009: projects lie at the fixed places of their consumers."""

from collections.abc import Iterable

from tools.conventions.context import Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.layout import RULESET_MODULE


class ProjectPlaces:
    info = RuleInfo(
        "RG009",
        "Projects lie at the fixed places of their consumers",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        yield from self.unplaced(context.workspace)
        yield from self.incomplete(context.workspace)

    @staticmethod
    def unplaced(workspace: Workspace) -> Iterable[Finding]:
        """Report configurations outside a project at a fixed place."""
        for path in sorted(workspace.godot_configurations):
            # The white-box fixtures of the ruleset module may live anywhere there, and a
            # `testdata` directory holds the input trees of a Go test, such as those of the
            # Gazelle language, which no consumer builds.
            ruleset = workspace.owner(path.as_posix()) == RULESET_MODULE
            if ruleset or "testdata" in path.parts:
                continue
            if workspace.project(path) is None:
                yield Finding(
                    Location(path.as_posix(), 1),
                    "Godot configurations must belong to a project at a fixed place "
                    "of their consumer",
                )

    @staticmethod
    def incomplete(workspace: Workspace) -> Iterable[Finding]:
        """Report projects without a BUILD file or a Godot configuration."""
        configurations = workspace.godot_configurations
        for project, members in workspace.projects.items():
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
