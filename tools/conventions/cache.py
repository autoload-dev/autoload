"""
The query cache: the output of each loading query the Bazel tool runs, stored under a key of
the query and of everything Bazel's loading reads, so that a run in which nothing loading reads
changed starts no Bazel server. The rules then evaluate the cached evidence as always.

The key covers the listed files and the contents of every one that loading can read; code that
builds compile and assets they package count by name only, since globs list them.
"""

import hashlib
import os
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
    return _digest(parts)


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
        key = _digest([self.inputs, str(workspace), *command])
        return self.directory / key[:2] / f"{key}.out"

    def run(
        self, workspace: Path, command: Sequence[str], query: Callable[[], str]
    ) -> str:
        """The command's cached output, or else ``query``'s, which is stored."""
        path = self._path(workspace, command)
        try:
            return path.read_text()
        except OSError:
            pass
        output = query()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(output)
        temporary.replace(path)
        return output
