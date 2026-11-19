"""RG009: project and add-on type and applicability follow the four typed roots."""

from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo


class TypedRootLayout:
    info = RuleInfo(
        "RG009",
        "Applications and add-ons use their typed roots",
        "docs/public/conventions.md#rg009",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        configurations = workspace.godot_configurations
        for path in sorted(configurations):
            # Consumer modules keep Godot configurations in their typed roots; the ruleset
            # module's white-box fixtures may live anywhere.
            if workspace.owner(path.as_posix()) == Path("."):
                continue
            if workspace.typed_directory(path) is not None:
                continue
            yield Finding(
                Location(path.as_posix(), 1),
                "Godot configurations must belong to a named project or add-on below projects/ or "
                "addons/ of their consumer module",
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
