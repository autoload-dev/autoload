"""
Lint the repository with every linter it has: Ruff and ty for Python, Buildifier's lint for
Starlark (its warnings as .buildifier.json selects them), jactionlint for the GitHub
workflows and `hk validate` for hk.pkl. Formatting is //tools/format's job, so no linter
here reports it.

With paths, as the pre-commit hook passes them, each linter checks only its own files among
them; ty then checks the whole project when a Python file is among them, since types cross
files. Without paths, every linter checks every file of the repository Git does not ignore.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

STARLARK_NAMES = {"BUILD", "BUILD.bazel", "MODULE.bazel", "WORKSPACE", "WORKSPACE.bazel"}
WORKFLOWS = ".github/workflows/"


@dataclass(frozen=True)
class Linters:
    """The pinned linters Bazel provides, and the repository they check."""

    ruff: Path
    ty: Path
    buildifier: Path
    root: Path


def is_python(path: str) -> bool:
    return path.endswith((".py", ".pyi"))


def is_starlark(path: str) -> bool:
    return path.endswith((".bzl", ".star")) or Path(path).name in STARLARK_NAMES


def is_workflow(path: str) -> bool:
    return path.startswith(WORKFLOWS) and path.endswith((".yml", ".yaml"))


def select(files: list[str], kind: Callable[[str], bool]) -> list[str]:
    return [path for path in files if kind(path)]


def run(command: list[str | Path], root: Path) -> int:
    return subprocess.run(command, cwd=root, check=False).returncode


def python(linters: Linters, files: list[str]) -> int:
    selected = select(files, is_python)
    if not selected:
        return 0
    status = run([linters.ruff, "check", "--force-exclude", *selected], linters.root)
    return status | run([linters.ty, "check"], linters.root)


def repository_files(root: Path) -> list[str]:
    """The repository's files that Git does not ignore, untracked ones included."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [path for path in listing.stdout.split("\0") if (root / path).is_file()]


def buildifier_findings(report: dict) -> list[str]:
    """Buildifier's lint warnings and invalid files, without its formatting verdicts."""
    findings = [
        f"{entry['filename']}: not valid Starlark"
        for entry in report["files"]
        if not entry.get("valid", True)
    ]
    findings += [
        f"{entry['filename']}:{warning['start']['line']}: {warning['category']}: "
        f"{warning['message']} ({warning['url']})"
        for entry in report["files"]
        for warning in entry.get("warnings", [])
    ]
    return findings


def starlark(linters: Linters, files: list[str]) -> int:
    selected = select(files, is_starlark)
    if not selected:
        return 0
    command = [linters.buildifier, "-mode=check", "-lint=warn", "-format=json", *selected]
    result = subprocess.run(
        command, cwd=linters.root, capture_output=True, text=True, check=False
    )
    if not result.stdout.strip():
        print(result.stderr, file=sys.stderr)
        return result.returncode or 1
    findings = buildifier_findings(json.loads(result.stdout))
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


def workflows(linters: Linters, files: list[str]) -> int:
    selected = select(files, is_workflow)
    if not selected:
        return 0
    command = [
        "mise",
        "exec",
        "jactionlint",
        "--",
        "jactionlint",
        "--shellcheck=",
        "--pyflakes=",
    ]
    return run([*command, *selected], linters.root)


def hk_config(linters: Linters, files: list[str]) -> int:
    if "hk.pkl" not in files:
        return 0
    # Through mise, like jactionlint: `bazel run` gives the linter no PATH with mise's tools.
    return run(["mise", "exec", "hk", "--", "hk", "validate"], linters.root)


def main() -> int:
    ruff, ty, buildifier = (Path(path).resolve() for path in sys.argv[1:4])
    root = Path(os.environ["BUILD_WORKSPACE_DIRECTORY"])
    linters = Linters(ruff, ty, buildifier, root)
    files = sys.argv[4:] or repository_files(root)
    status = 0
    for lint in (python, starlark, workflows, hk_config):
        status |= lint(linters, files)
    return status


if __name__ == "__main__":
    sys.exit(main())
