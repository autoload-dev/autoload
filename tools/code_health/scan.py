"""Scanning files with the CodeScene CLI, including languages it lacks.

The CodeScene CLI `cs`, which Bazel pins (multitool.lock.json), reviews every file under a *virtual*
file name, so files CodeScene does not know are analysed as a language it does
(translation.py), in one run with each result cached (batch.py). Nothing in the repository
is modified; results are reported under the original paths and lines.

Code Health rules: a code-health-rules.json passed with --rules, else the repository's own
.codescene/code-health-rules.json. Its matching_content_path globs see the virtual names,
e.g. "**/*.bzl.py" for Starlark and "**/*.gd.py" for GDScript.

Requirements: `cs` named by CODESCENE_CLI, as `aspect code-health` names it, or on PATH,
and either a personal access token in CS_ACCESS_TOKEN or a `cs auth login` session. The
token is never printed.

Sections: Environment, File selection, Scanning.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from tools.code_health.batch import Reviewer
from tools.code_health.macros import MAX_ARGUMENTS
from tools.code_health.translation import (
    NATIVE,
    Translation,
    original_title,
    translate,
)

LANGUAGE = {
    ".py": "Python",
    ".pyi": "Python",
    ".bzl": "Starlark",
    ".gd": "GDScript",
    ".c": "C/C++",
    ".cc": "C/C++",
    ".cpp": "C/C++",
    ".cxx": "C/C++",
    ".h": "C/C++",
    ".hh": "C/C++",
    ".hpp": "C/C++",
    ".hxx": "C/C++",
    ".m": "Objective-C",
    ".mm": "Objective-C",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".dart": "Dart",
    ".go": "Go",
    ".rs": "Rust",
}
BUILD_FILE = re.compile(
    r"(^|/)(BUILD|BUILD\.bazel|MODULE\.bazel|WORKSPACE(\.bazel)?)$|\.star$"
)
DEFAULT_EXCLUDES = [
    "*/third_party/*",
    "*/vendor/*",
    "*/node_modules/*",
]


def loc(source: str) -> int:
    return sum(
        1
        for line in source.splitlines()
        if line.strip() and not line.strip().startswith(("#", "//"))
    )


@dataclass
class FileResult:
    path: str
    language: str
    loc: int
    score: float | None
    smells: list[dict] = field(default_factory=list)
    macros: list[str] = field(default_factory=list)
    error: str | None = None  # why the CodeScene CLI could not score the file


# ==== Environment =============================================================


class Unavailable(Exception):
    """The CodeScene CLI or its token is missing, so nothing can be scored."""


def find_cli() -> str:
    """The CodeScene CLI: CODESCENE_CLI, as `aspect code-health` sets it, else `cs` on PATH."""
    cli = os.environ.get("CODESCENE_CLI") or shutil.which("cs")
    if not cli:
        raise Unavailable(
            "CodeScene CLI `cs` not found: run `aspect code-health`, which provides it, "
            "or set CODESCENE_CLI"
        )
    return cli


def cli_environment(cli: str) -> dict[str, str]:
    """The CLI's environment, once it can sign in: with CS_ACCESS_TOKEN or `cs auth`."""
    env = dict(os.environ, CS_DISABLE_VERSION_CHECK="1")
    if env.get("CS_ACCESS_TOKEN"):
        return env
    status = subprocess.run(
        [cli, "auth", "status"], capture_output=True, env=env, check=False
    )
    if status.returncode != 0:
        raise Unavailable(
            "CodeScene is not signed in: set CS_ACCESS_TOKEN to a personal access token, "
            "or run `cs auth login` once"
        )
    return env


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )


def git(repo: Path, *args: str) -> str:
    """Git's output, or exit with its error."""
    result = run_git(repo, *args)
    if result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


# ==== File selection ==========================================================


def is_analysable(path: str, include_build: bool) -> bool:
    suffix = Path(path).suffix
    return (
        suffix in NATIVE
        or suffix in (".bzl", ".gd")
        or bool(include_build and BUILD_FILE.search(path))
    )


def is_selected(path: str, include_build: bool, excludes: list[str]) -> bool:
    """Whether the path is a file to score: analysable and not excluded."""
    if not is_analysable(path, include_build):
        return False
    return not any(fnmatch.fnmatch(path, pattern) for pattern in excludes)


def in_commit(repo: Path, ref: str, path: str) -> bool:
    """Whether the path is a file at the ref."""
    return run_git(repo, "cat-file", "-e", f"{ref}:{path}").returncode == 0


def worktree_files(repo: Path, include_build: bool, excludes: list[str]) -> list[str]:
    """The files of the working tree to score, untracked ones included."""
    listing = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted(
        {
            path
            for path in filter(None, listing.split("\0"))
            if is_selected(path, include_build, excludes) and (repo / path).is_file()
        }
    )


def language_of(path: str) -> str:
    if BUILD_FILE.search(path):
        return "Starlark (BUILD)"
    return LANGUAGE.get(Path(path).suffix, Path(path).suffix.lstrip(".") or "other")


# ==== Scanning ================================================================


def smells_of(data: dict, translation: Translation) -> list[dict]:
    """The CLI's findings, with the functions and lines of the original file."""
    return [
        {
            "category": item["category"],
            "functions": [
                {
                    "name": original_title(f.get("title", ""), translation),
                    "start": translation.original_line(f.get("start-line")),
                    "end": translation.original_line(f.get("end-line")),
                    "details": f.get("details", ""),
                }
                for f in item.get("functions", [])
            ],
        }
        for item in data.get("review", [])
    ]


def file_result(
    path: str, source: str, translation: Translation, result: dict
) -> FileResult:
    """A file's result from what the CLI answered for its translation."""
    error = result.get("error")
    if error:
        print(f"warning: {path}: {error}", file=sys.stderr)
    return FileResult(
        path,
        language_of(path),
        loc(source),
        result.get("score"),
        smells_of(result, translation),
        macros=translation.macros,
        error=error,
    )


@dataclass
class Scanner:
    reviewer: Reviewer
    macro_arguments: bool
    repo: Path

    def source_of(self, ref: str | None, path: str) -> str:
        """The file at the ref, in the index for "", or in the working tree for None."""
        if ref is None:
            return (self.repo / path).read_text(errors="replace")
        return git(self.repo, "show", f"{ref}:{path}")

    def scan(self, files: list[tuple[str | None, str]]) -> list[FileResult]:
        """Score each (ref, path), at the ref or, without one, in the working tree."""
        with ThreadPoolExecutor() as pool:
            sources = list(pool.map(lambda file: self.source_of(*file), files))
        translations = [
            translate(path, source, self.macro_arguments)
            for (_, path), source in zip(files, sources, strict=True)
        ]
        results = self.reviewer.review(translations)
        return [
            file_result(path, source, translation, result)
            for (_, path), source, translation, result in zip(
                files, sources, translations, results, strict=True
            )
        ]


def rules_of(repo: Path, rules: Path | None) -> tuple[str | None, str]:
    """The Code Health rules to apply, the repository's own unless given, and their source."""
    if rules is not None and not rules.is_file():
        sys.exit(f"--rules: no such file: {rules}")
    path = rules or repo / ".codescene" / "code-health-rules.json"
    if not path.is_file():
        return None, "CodeScene defaults"
    source = str(rules) if rules else f"repository's {path.relative_to(repo)}"
    return path.read_text(), source


def scan_notes(
    results: list[FileResult], keep_macro_arguments: bool, rules_source: str
) -> list[str]:
    """What a report should say about how its files were scored."""
    macros = sum(len(r.macros) for r in results)
    return [
        f"Code Health rules: {rules_source}.",
        "Bazel macro parameters counted like any function's."
        if keep_macro_arguments
        else f"{macros} Bazel macros with more than {MAX_ARGUMENTS} parameters exempt from "
        "Excess Number of Function Arguments: their parameters mirror rule attributes, "
        "which CodeScene does not count either.",
    ]
