"""RG009: project and add-on type and applicability follow the four typed roots."""

from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.layout import RULESET_MODULE, is_addon_test


def _white_box(workspace: Workspace, path: Path) -> bool:
    """
    Whether a configuration is a fixture: the ruleset's, one of an add-on module's own tests
    in its tests/, or of an add-on module's end-to-end tests.
    """
    owner = workspace.owner(path.as_posix())
    if owner == RULESET_MODULE:
        return True
    if owner.parent == Path("addons") and path.relative_to(owner).parts[:1] == ("tests",):
        return True
    return is_addon_test(workspace.consumer_root(path))


class TypedRootLayout:
    info = RuleInfo(
        "RG009",
        "Applications and add-ons use their typed roots",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        configurations = workspace.godot_configurations
        for path in sorted(configurations):
            # Consumer modules keep Godot configurations in their typed roots; white-box
            # fixtures of the ruleset module, and the fixtures of an add-on module's tests in
            # its examples/tests/, may live anywhere there.
            if _white_box(workspace, path):
                continue
            if workspace.typed_directory(path) is not None:
                continue
            yield Finding(
                Location(path.as_posix(), 1),
                "Godot configurations must belong to a named project or add-on of their consumer",
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
