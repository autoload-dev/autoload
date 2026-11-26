"""
Evaluate Pkl modules with the pinned Pkl CLI (//:multitool.lock.json), so that the tools read
what Pkl means rather than parse its syntax.

The CLI is PKL_CLI, as the Aspect CLI's tasks name it (.aspect/work.axl), else the one in the
runfiles of a Bazel target that depends on this library, else the one Bazel builds for a
tool run directly, such as `python3 -m tools.addons.selftest`.
"""

import functools
import json
import os
import subprocess
from pathlib import Path
from typing import Any

# The CLI's target and runfiles path, through the repository mapping of the root module.
TARGET = "@multitool//tools/pkl"
RUNFILES_PATH = "multitool/tools/pkl/pkl"
ROOT = Path(__file__).resolve().parents[2]


def resolve_task_cli() -> None:
    """
    Resolve PKL_CLI to the file it names, for this process and the tools it starts. The task
    names the CLI through the bazel-out symlink, which a later Bazel command of another
    profile repoints to that profile's output base.
    """
    if (path := os.environ.get("PKL_CLI")) and os.path.exists(path):
        os.environ["PKL_CLI"] = os.path.realpath(path)


resolve_task_cli()


class PklError(RuntimeError):
    """A Pkl module that does not evaluate, such as one whose values break its schema."""


def runfile() -> str | None:
    """The CLI in this process's runfiles, when Bazel runs it."""
    try:
        from python.runfiles import runfiles
    except ImportError:
        return None
    found = runfiles.Create()
    path = found.Rlocation(RUNFILES_PATH) if found is not None else None
    return path if path is not None and Path(path).is_file() else None


def built() -> str:
    """The CLI as Bazel builds it in the repository's root module."""
    try:
        subprocess.run(
            ["bazel", "build", TARGET], cwd=ROOT, capture_output=True, check=True
        )
        files = subprocess.run(
            ["bazel", "cquery", "--output=files", TARGET],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise PklError(f"no Pkl CLI: building {TARGET} failed: {error}") from error
    return str(ROOT / files.stdout.strip())


@functools.cache
def cli() -> str:
    """The path of the Pkl CLI."""
    if (path := os.environ.get("PKL_CLI")) and os.path.exists(path):
        return path
    if (path := runfile()) is not None:
        return path
    return built()


def first_line(text: str) -> str:
    """A Pkl module's first line, after comments, such as the one that amends its schema."""
    lines = (line.split("//")[0].strip() for line in text.splitlines())
    return next((line for line in lines if line), "")


def evaluate(path: Path, expression: str | None = None) -> Any:
    """A Pkl module's value as JSON data, or that of an expression in it."""
    command = [cli(), "eval", "--no-cache"]
    if expression is None:
        command += ["--format", "json"]
    else:
        command += ["--expression", f"new JsonRenderer {{}}.renderValue({expression})"]
    result = subprocess.run(
        [*command, str(path)], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise PklError(f"{path}: {result.stderr.strip()}")
    return json.loads(result.stdout)


@functools.cache
def _evaluated(path: Path, text: str) -> dict[str, Any]:
    """The evaluation of one manifest's text."""
    return evaluate(path)


def manifest(path: Path, amends: str) -> dict[str, Any]:
    """
    A manifest that amends a schema, as Pkl evaluates it with the schema's defaults and
    types, once per process and text; one that does not amend the schema does not evaluate.
    """
    text = path.read_text()
    if first_line(text) != amends:
        raise PklError(f"{path}: starts with {amends}")
    return _evaluated(path, text)
