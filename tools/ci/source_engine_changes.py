"""
Whether a pull request reaches the source-engine tests, for the Source engine workflow
(.github/workflows/source-engine.yml), which runs them on such a pull request by itself.

A change reaches them when it touches what builds a source engine or the tests themselves:
the engine recipes and repositories (rules_godot/godot/engine) and their tools
(rules_godot/tools/engine), the engines of the examples and of the patched-engine scenario
with their lock files, modules and patches, the workflow and this file, and each package that
declares a test tagged `source_engine`, with its subpackages. The tagged packages are read
from the BUILD files, so a new source-engine test is covered without an edit here; a watched
path that no longer exists fails the run, so that the list follows a move.

MODULE.bazel files, which register the engines, are not watched: most pull requests change
them. A changed registration of a pinned engine changes its lock file, which is.

    python3 -m tools.ci.source_engine_changes <base> <head>

prints the files that reach the tests and, in a GitHub Actions step, sets the step's output
`reaches` to `true` or `false`.
"""

import os
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

# What builds a source engine; a directory ends with a slash.
ENGINE_PATHS = (
    "rules_godot/godot/engine/",
    "rules_godot/godot/extensions.bzl",
    "rules_godot/tools/engine/",
    "examples/engines/",
    "e2e/rules_godot/patched_engine/",
    ".github/workflows/source-engine.yml",
    "tools/ci/source_engine_changes.py",
)

# The tag of the tests that build an engine from source (shared.bazelrc).
_TAG = '"source_engine"'


def _git(root: Path, *arguments: str) -> list[str]:
    output = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    return [line for line in output.split("\0") if line]


def watched(root: Path) -> list[str]:
    """The watched paths of the checkout at `root`: the engine paths and the tagged packages."""
    files = _git(root, "ls-files", "-z")
    missing = [p for p in ENGINE_PATHS if not any(f.startswith(p) for f in files)]
    if missing:
        raise FileNotFoundError(
            f"watched paths that no longer exist: {', '.join(missing)}"
        )
    tagged = [
        path.removesuffix("BUILD.bazel")
        for path in files
        if path.rsplit("/", 1)[-1] == "BUILD.bazel"
        and _TAG in (root / path).read_text(errors="replace")
    ]
    return [*ENGINE_PATHS, *tagged]


def reaching(changed: Iterable[str], paths: Sequence[str]) -> list[str]:
    """The changed files below a watched directory or equal to a watched file."""
    return [
        file
        for file in changed
        if any(
            file == path or (path.endswith("/") and file.startswith(path))
            for path in paths
        )
    ]


def main(argv: list[str]) -> int:
    base, head = argv
    root = Path.cwd()
    changed = _git(root, "diff", "-z", "--name-only", f"{base}...{head}")
    found = reaching(changed, watched(root))
    print("\n".join(found) if found else "No change reaches the source-engine tests.")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as file:
            file.write(f"reaches={'true' if found else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
