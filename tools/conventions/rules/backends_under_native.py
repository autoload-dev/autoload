"""
backends-under-native: in every add-on, its examples' included, a backends/ directory sits
in native/, beside the platform-independent API it implements.
"""

from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo


def backends_directory(name: str) -> Path | None:
    """The first backends/ directory of a path that is not an add-on's native/backends/."""
    parts = Path(name).parts
    for index, part in enumerate(parts[:-1]):
        previous = parts[index - 1] if index else ""
        if part == "backends" and previous != "native":
            return Path(*parts[: index + 1])
    return None


class BackendsUnderNative:
    info = RuleInfo(
        "backends-under-native",
        "An add-on's backends live in its native/backends/",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        misplaced: dict[Path, str] = {}
        for name in context.workspace.files:
            if (directory := backends_directory(name)) is not None:
                misplaced.setdefault(directory, name)
        for directory, name in sorted(misplaced.items()):
            yield Finding(
                Location(name, 1),
                f"an add-on's backends belong in its native/backends/: {directory.as_posix()}",
            )
