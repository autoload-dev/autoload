"""RG010: complete add-ons own separate demo and Godot test projects."""

from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo


class AddonProjects:
    info = RuleInfo(
        "RG010",
        "Add-ons separate demo and Godot test projects",
        "docs/public/conventions.md#rg010",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        for root, members in workspace.typed_directories("addons").items():
            location = Location(members[0], 1)
            for directory in (root, root / "demo", root / "tests"):
                if not workspace.has_build(directory):
                    yield Finding(
                        location, f"add-on scope must own a BUILD file: {directory}"
                    )
            expected = {root / "demo/project.godot", root / "tests/project.godot"}
            for config in sorted(expected):
                if config.as_posix() not in workspace.file_set:
                    yield Finding(
                        location, f"add-on must own a separate project: {config}"
                    )
            for name in members:
                if Path(name).name == "project.godot" and Path(name) not in expected:
                    yield Finding(
                        Location(name, 1),
                        "add-on Godot configurations belong at demo/project.godot or "
                        "tests/project.godot; reuse those contexts for suite categories",
                    )
