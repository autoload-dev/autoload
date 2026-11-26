"""
The query cache: the output of each loading query the Bazel tool runs, stored under a key of
the query and of everything Bazel's loading reads, so that a run in which nothing loading reads
changed starts no Bazel server. The rules then evaluate the cached evidence as always.

An entry also records the external repositories its output names, in the output base; when
one of them is gone, such as after `bazel clean --expunge`, the entry misses.

The key covers the listed files and the contents of every one that loading can read; code that
builds compile and assets they package count by name only, since globs list them. The ignored
Bazel rc files that the workspace imports count as well; the environment does not. Entries are
compressed, and only those of the most recent loading inputs are kept.
"""

import gzip
import hashlib
import json
import os
import re
import shutil
import threading
from collections.abc import Callable, Sequence
from functools import cached_property
from pathlib import Path

from tools.conventions.context import Workspace

# Files whose contents Bazel's loading never reads: code that builds compile and assets they
# package. An unknown suffix counts as read.
INERT_SUFFIXES = frozenset(
    {
        ".bin",
        ".c",
        ".cc",
        ".cpp",
        ".dart",
        ".dylib",
        ".gd",
        ".gltf",
        ".h",
        ".hpp",
        ".import",
        ".java",
        ".js",
        ".kt",
        ".m",
        ".mm",
        ".pck",
        ".png",
        ".py",
        ".so",
        ".storyboard",
        ".svg",
        ".swift",
        ".tres",
        ".tscn",
        ".ttf",
        ".uid",
    }
)


# The rc files outside the listing that Bazel reads: the user's own, and the checkout's ignored
# user.bazelrc, which .bazelrc imports.
RC_FILES = (Path.home() / ".bazelrc", Path("user.bazelrc"))
# How many sets of loading inputs keep their entries; worktrees share the cache.
KEPT = 8
# A path into a repository of Bazel's external directory, in the output base.
EXTERNAL = re.compile(r"/[^\s\"':]*/external/[^/\s\"':]+")


def cache_directory() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "autoload" / "conventions"


def _digest(parts: Sequence[str | bytes]) -> str:
    """An unambiguous digest of the parts: each is prefixed with its length."""
    digest = hashlib.sha256()
    for part in parts:
        data = part.encode() if isinstance(part, str) else part
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def loading_inputs(workspace: Workspace) -> str:
    """The digest of what Bazel's loading can read in the workspace."""
    parts: list[str | bytes] = []
    for name in workspace.entries:
        path = workspace.root / name
        if name not in workspace.file_set:
            parts += ["link", name, os.readlink(path)]
        elif Path(name).suffix in INERT_SUFFIXES:
            parts += ["file", name]
        else:
            parts += ["file", name, path.read_bytes()]
    for rc in RC_FILES:
        path = workspace.root / rc
        parts += ["rc", str(rc), path.read_bytes() if path.is_file() else b""]
    return _digest(parts)


def external_paths(output: str) -> list[str]:
    """The paths of external repositories in the output base that query output names."""
    return sorted(set(EXTERNAL.findall(output)))


class QueryCache:
    """Query output by query and loading inputs, one file each; an unreadable entry misses."""

    def __init__(self, directory: Path, inputs: Callable[[], str]) -> None:
        """``inputs`` gives the digest of the loading inputs; it is computed once, when needed."""
        self.directory = directory
        self._inputs = inputs

    @cached_property
    def inputs(self) -> str:
        return self._inputs()

    def _path(self, workspace: Path, command: Sequence[str]) -> Path:
        key = _digest([str(workspace), *command])
        return self.directory / self.inputs / f"{key}.gz"

    def run(
        self, workspace: Path, command: Sequence[str], query: Callable[[], str]
    ) -> str:
        """The command's cached output, or else ``query``'s, which is stored."""
        path = self._path(workspace, command)
        cached = self._read(path)
        if cached is not None:
            return cached
        output = query()
        # Storing is best effort: another checker may prune the same directory meanwhile.
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            entry = json.dumps(external_paths(output)) + "\n" + output
            temporary.write_bytes(gzip.compress(entry.encode(), compresslevel=1))
            temporary.replace(path)
            self._prune()
        except OSError:
            pass
        return output

    @staticmethod
    def _read(path: Path) -> str | None:
        """
        An entry's output; none when it is unreadable or names an external repository that
        is gone, such as after the output base was cleaned.
        """
        try:
            header, _, output = (
                gzip.decompress(path.read_bytes()).decode().partition("\n")
            )
            paths = json.loads(header)
        except OSError, EOFError, ValueError:
            return None
        return output if all(map(os.path.exists, paths)) else None

    def _prune(self) -> None:
        """Remove the entries of all but the most recent sets of loading inputs."""
        sets = sorted(
            (entry for entry in self.directory.iterdir() if entry.is_dir()),
            key=lambda entry: entry.stat().st_mtime,
            reverse=True,
        )
        for entry in sets[KEPT:]:
            shutil.rmtree(entry, ignore_errors=True)
