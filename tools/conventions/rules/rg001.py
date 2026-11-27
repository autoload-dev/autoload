"""RG001: owned Bazel package segments use lower snake case."""

from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import BUILD_FILES, Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.naming import LOWER_SNAKE_CASE


def package_path(workspace: Workspace, build: Path) -> Path | None:
    """
    The package of a BUILD file relative to its nearest module, from the files beside it on
    disk; None in a repository below a module that is no module itself.
    """
    for directory in build.parents:
        if (workspace.root / directory / "MODULE.bazel").is_file():
            return build.parent.relative_to(directory)
        if (workspace.root / directory / "REPO.bazel").is_file():
            return None
    return None


def misspelled_segments(workspace: Workspace, name: str) -> Iterable[str]:
    """
    The package segments of a BUILD file that are not lower snake case, each once however
    often the package repeats it; none for any other file.
    """
    build = Path(name)
    package = package_path(workspace, build) if build.name in BUILD_FILES else None
    segments = dict.fromkeys(package.parts) if package else ()
    return (segment for segment in segments if not LOWER_SNAKE_CASE.fullmatch(segment))


class PackageNames:
    info = RuleInfo(
        "RG001",
        "Package segments use lower snake case",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        for name in workspace.files:
            for segment in misspelled_segments(workspace, name):
                yield Finding(
                    Location(name, 1),
                    f"package segment {segment!r} must use lower_snake_case",
                )
