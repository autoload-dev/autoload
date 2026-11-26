"""
The result cache of the rules that read Bazel's loading evidence: their diagnostics, stored
under a key of everything that can change them, so that a run without such a change starts no
Bazel server. The key covers the checker's own code, the selected rules, the listed files and
the contents of every listed file that can change what Bazel loads or what the rules read;
the sources and assets that only builds compile or package, such as Python or GDScript, are
left out, as only their names matter to loading.
"""

import hashlib
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Location, Workspace
from tools.conventions.framework import Diagnostic, Finding, Rule

# Files whose contents no loading query reads: code that builds compile and assets they
# package. Their names still count, since globs list them.
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


def checker_sources() -> tuple[Path, ...]:
    """The repository's Python modules that this process has loaded: the checker and its rules."""
    tools = Path(__file__).resolve().parents[1]
    files = (getattr(module, "__file__", None) for module in list(sys.modules.values()))
    return tuple(
        sorted(
            {
                path
                for file in files
                if file and (path := Path(file).resolve()).is_relative_to(tools)
            }
        )
    )


def evidence_key(
    workspace: Workspace, rules: Iterable[Rule], checker: Iterable[Path]
) -> str:
    """The key of the rules' diagnostics in this workspace, run by this checker."""
    digest = hashlib.sha256()

    def add(*parts: str | bytes) -> None:
        for part in parts:
            data = part.encode() if isinstance(part, str) else part
            digest.update(len(data).to_bytes(8, "big") + data)

    add(*(rule.info.id for rule in rules))
    for path in checker:
        add(path.name, path.read_bytes())
    for name in workspace.entries:
        path = workspace.root / name
        if name not in workspace.file_set:
            add("link", name, os.readlink(path))
            continue
        add("file", name)
        if Path(name).suffix not in INERT_SUFFIXES:
            add(path.read_bytes())
    return digest.hexdigest()


def encode(diagnostics: Iterable[Diagnostic]) -> str:
    return json.dumps(
        [
            {
                "rule": item.rule.id,
                "path": item.finding.location.path,
                "line": item.finding.location.line,
                "message": item.finding.message,
                "status": item.finding.status,
                "required": item.finding.required,
            }
            for item in diagnostics
        ]
    )


def decode(text: str, rules: Iterable[Rule]) -> tuple[Diagnostic, ...]:
    infos = {rule.info.id: rule.info for rule in rules}
    return tuple(
        Diagnostic(
            infos[item["rule"]],
            Finding(
                Location(item["path"], item["line"]),
                item["message"],
                item["status"],
                item["required"],
            ),
        )
        for item in json.loads(text)
    )


class ReportCache:
    """Diagnostics by key, one file each; an unreadable entry counts as missing."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key}.json"

    def load(self, key: str, rules: Iterable[Rule]) -> tuple[Diagnostic, ...] | None:
        try:
            return decode(self._path(key).read_text(), rules)
        except OSError, ValueError, KeyError:
            return None

    def store(self, key: str, diagnostics: Iterable[Diagnostic]) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(encode(diagnostics))
        temporary.replace(path)
