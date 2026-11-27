"""
engine-files-under-engines: a consumer's engine modules, patches and lock files sit under
engines/<name>/.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from tools.conventions.context import (
    BUILD_FILES,
    Context,
    Location,
    Workspace,
    nearest,
)
from tools.conventions.framework import Finding, RuleInfo

PATCH_SUFFIXES = frozenset({".patch", ".diff"})
MODULE_FILES = frozenset({"config.py", "SCsub"})
ENGINES = "engines"
# An engine's lock file, as its godot_engines.engine names it: <engine>.lock.json.
LOCK_SUFFIX = ".lock.json"
ENGINE_ENTRIES = (
    "an engines/<name>/ directory holds only modules/, patches/, a BUILD file, lock files, "
    ".bzl files and a README.md"
)


def is_engine_file(name: str) -> bool:
    """A file engines/<name>/ may hold directly: BUILD, a lock file, .bzl or a README."""
    return (
        name in BUILD_FILES or name == "README.md" or name.endswith((LOCK_SUFFIX, ".bzl"))
    )


def is_module(files: Iterable[str]) -> bool:
    """
    Recognize an engine module placed anywhere: config.py beside SCsub or
    register_types.*. Under engines/<name>/modules/ the complete pair is required.
    """
    names = set(files)
    return "config.py" in names and (
        "SCsub" in names or any(name.startswith("register_types.") for name in names)
    )


def engine_directory(path: Path) -> Path | None:
    """The engines/<name>/ directory a file lies in, wherever engines/ is, or None."""
    for index, part in enumerate(path.parts[:-2]):
        if part == ENGINES:
            return Path(*path.parts[: index + 2])
    return None


def is_patch_file(path: Path) -> bool:
    """A file engines/<name>/patches/ may hold: a patch or its BUILD file."""
    return path.suffix in PATCH_SUFFIXES or path.name in BUILD_FILES


@dataclass(frozen=True)
class Entry:
    """One entry of an engines/<name>/ directory, or of its modules/ or patches/."""

    engine: Path
    key: tuple[str, ...]
    first: Path
    own_files: frozenset[str]

    @property
    def is_directory(self) -> bool:
        return len(self.first.parts) > len(self.key)

    @property
    def shown(self) -> str:
        suffix = "/" if self.is_directory else ""
        return f"{ENGINES}/{self.engine.name}/" + "/".join(self.key) + suffix


def module_problem(entry: Entry) -> str | None:
    if not entry.is_directory:
        return (
            "engines/<name>/modules/ holds only engine module directories; "
            f"unexpected entry: {entry.shown}"
        )
    if MODULE_FILES <= entry.own_files:
        return None
    return (
        "engine module directory must own config.py and SCsub: "
        f"{(entry.engine / Path(*entry.key)).as_posix()}"
    )


def patch_problem(entry: Entry) -> str | None:
    if not entry.is_directory and is_patch_file(entry.first):
        return None
    return (
        "engines/<name>/patches/ holds only .patch and .diff files and a BUILD file; "
        f"unexpected entry: {entry.shown}"
    )


def entry_problem(entry: Entry) -> str | None:
    """What is wrong with an entry of an engine directory, or None."""
    if entry.key[0] == "modules":
        return module_problem(entry)
    if entry.key[0] == "patches":
        return patch_problem(entry)
    if not entry.is_directory and is_engine_file(entry.key[0]):
        return None
    return f"{ENGINE_ENTRIES}; unexpected entry: {entry.shown}"


def entries_of(engine: Path, files: list[Path]) -> list[Entry]:
    """
    The entries of an engine directory, given its relative files: one per entry of the
    directory, and per entry of modules/ and patches/.
    """
    directories: dict[Path, set[str]] = defaultdict(set)
    grouped: dict[tuple[str, ...], list[Path]] = defaultdict(list)
    for relative in files:
        directories[relative.parent].add(relative.name)
        depth = 2 if relative.parts[0] in ("modules", "patches") else 1
        grouped[relative.parts[:depth]].append(relative)
    return [
        Entry(engine, key, paths[0], frozenset(directories[Path(*key)]))
        for key, paths in sorted(grouped.items())
    ]


def project_problem(path: Path, projects: list[Path]) -> str | None:
    """What is wrong with a file of a Godot project that lies outside engines/<name>/."""
    if nearest(path, projects) is None:
        return None
    if path.suffix in PATCH_SUFFIXES:
        return (
            "engine patch must live under engines/<name>/patches/, not in a Godot project"
        )
    if path.name.endswith(LOCK_SUFFIX):
        return (
            "an engine's lock file must live under engines/<name>/, "
            "not in a Godot project"
        )
    return None


def misplaced_modules(files: list[Path]) -> Iterable[Path]:
    """The engine module directories among files that lie outside engines/<name>/."""
    directories: dict[Path, set[str]] = defaultdict(set)
    for path in files:
        directories[path.parent].add(path.name)
    return [
        directory for directory, names in sorted(directories.items()) if is_module(names)
    ]


def partition(workspace: Workspace) -> tuple[dict[Path, list[Path]], list[Path]]:
    """
    Split the files of the consumer modules into those of each engines/<name>/ directory,
    relative to it, and the rest.
    """
    engines: dict[Path, list[Path]] = defaultdict(list)
    outside: list[Path] = []
    for name in workspace.files:
        path = Path(name)
        if workspace.consumer_root(path) is None:
            continue
        engine = engine_directory(path)
        if engine is None:
            outside.append(path)
        else:
            engines[engine].append(path.relative_to(engine))
    return engines, outside


def finding(path: Path, message: str) -> Finding:
    return Finding(Location(path.as_posix(), 1), message)


class EngineLayout:
    info = RuleInfo(
        "engine-files-under-engines",
        "Engine modules, patches and lock files live under engines/<name>/",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        engines, outside = partition(workspace)
        projects = sorted(
            config.parent
            for config in workspace.godot_configurations
            if workspace.consumer_root(config) is not None
        )
        yield from self.check_outside(sorted(outside), projects)
        for engine, files in sorted(engines.items()):
            for entry in entries_of(engine, sorted(files)):
                if (message := entry_problem(entry)) is not None:
                    yield finding(engine / entry.first, message)

    @staticmethod
    def check_outside(files: list[Path], projects: list[Path]) -> Iterable[Finding]:
        """Report what belongs in an engines/<name>/ directory but lies elsewhere."""
        for path in files:
            if (message := project_problem(path, projects)) is not None:
                yield finding(path, message)
        for directory in misplaced_modules(files):
            yield finding(
                directory / "config.py",
                "engine module must live under engines/<name>/modules/: "
                f"{directory.as_posix()}",
            )
