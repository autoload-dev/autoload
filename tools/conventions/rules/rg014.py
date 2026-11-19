"""RG014: a project's engine modules and patches sit under its engine/ directory."""

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import BUILD_FILES, Context, Location, nearest
from tools.conventions.framework import Finding, RuleInfo

PATCH_SUFFIXES = frozenset({".patch", ".diff"})
MODULE_FILES = frozenset({"config.py", "SCsub"})


def is_module(files: Iterable[str]) -> bool:
    """
    Recognize an engine module placed anywhere: config.py beside SCsub or
    register_types.*. Under engine/modules/ the complete pair is required.
    """
    names = set(files)
    return "config.py" in names and (
        "SCsub" in names or any(name.startswith("register_types.") for name in names)
    )


class EngineLayout:
    info = RuleInfo(
        "RG014",
        "Engine modules and patches live under engine/",
        "docs/public/conventions.md#rg014",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        roots = sorted(
            config.parent
            for config in workspace.godot_configurations
            if workspace.owner(config.as_posix()) != Path(".")
        )
        members: dict[Path, list[Path]] = defaultdict(list)
        for name in workspace.files:
            path = Path(name)
            owner = nearest(path, roots)
            if owner is not None:
                members[owner].append(path.relative_to(owner))
        for root in roots:
            yield from self.check_project(root, sorted(members[root]))

    def check_project(self, root: Path, files: list[Path]) -> Iterable[Finding]:
        """Check one project's root-relative files."""
        directories: dict[Path, set[str]] = defaultdict(set)
        for relative in files:
            directories[relative.parent].add(relative.name)
        for relative in files:
            if relative.parts[0] != "engine" and relative.suffix in PATCH_SUFFIXES:
                yield self.finding(
                    root,
                    relative,
                    "engine patch must live under engine/patches/ of its project",
                )
        for directory, names in sorted(directories.items()):
            if directory.parts[:1] != ("engine",) and is_module(names):
                yield self.finding(
                    root,
                    directory / "config.py",
                    "engine module must live under engine/modules/ of its project: "
                    f"{(root / directory).as_posix()}",
                )
        # One finding per entry of engine/, and per entry of modules/ and patches/.
        entries: dict[tuple[str, ...], list[Path]] = defaultdict(list)
        for relative in files:
            if relative.parts[0] == "engine" and len(relative.parts) > 1:
                depth = 3 if relative.parts[1] in ("modules", "patches") else 2
                entries[relative.parts[1:depth]].append(relative)
        for key, paths in sorted(entries.items()):
            first = paths[0]
            is_directory = len(first.parts) > len(key) + 1
            shown = "engine/" + "/".join(key) + ("/" if is_directory else "")
            if key[0] not in ("modules", "patches"):
                yield self.finding(
                    root,
                    first,
                    f"engine/ holds only modules/ and patches/; unexpected entry: {shown}",
                )
            elif key[0] == "modules":
                if not is_directory:
                    yield self.finding(
                        root,
                        first,
                        "engine/modules/ holds only engine module directories; "
                        f"unexpected entry: {shown}",
                    )
                elif not MODULE_FILES <= directories[Path(*first.parts[:3])]:
                    yield self.finding(
                        root,
                        first,
                        "engine module directory must own config.py and SCsub: "
                        f"{(root / shown.rstrip('/')).as_posix()}",
                    )
            elif is_directory or (
                first.suffix not in PATCH_SUFFIXES and first.name not in BUILD_FILES
            ):
                yield self.finding(
                    root,
                    first,
                    "engine/patches/ holds only .patch and .diff files and a BUILD file; "
                    f"unexpected entry: {shown}",
                )

    @staticmethod
    def finding(root: Path, relative: Path, message: str) -> Finding:
        return Finding(Location((root / relative).as_posix(), 1), message)
