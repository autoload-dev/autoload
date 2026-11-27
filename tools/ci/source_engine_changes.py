"""
Whether a pull request reaches the source-engine tests, for the Source engine workflow
(.github/workflows/source-engine.yml), which runs them on such a pull request by itself.

A change reaches them when it touches what builds a source engine or the tests themselves:
the engine recipes and repositories (rules_godot/godot/engine) and their tools
(rules_godot/tools/engine), the engines of the examples and of the patched-engine scenario
with their lock files, modules and patches, the workflow and this file, and each package that
declares a test tagged `source_engine`, with its subpackages, or for an example's package
the whole example. The tagged packages are read
from the BUILD files, so a new source-engine test is covered without an edit here; a watched
path that no longer exists fails the run, so that the list follows a move.

Most pull requests change a MODULE.bazel file, so the two that register source engines, the
root module's and the ruleset's, reach the tests only where a change touches a registration:
a hunk that names a call of `godot_engine*` or `godot_android_shell`, or one of the private
constants those calls take, which these files hold for nothing else. Code that every build
shares, such as the ruleset's rules or shared.bazelrc, is not watched; a pull request that
may break source-built engines through it carries the label, as does one that changes how
the workflow runs the tests: the work `source-engine:full` and `source-engine:linux`
(tools/ci/work.py) and the configs `source-engine` of the bazelrc files.

    python3 -m tools.ci.source_engine_changes <base> <head>

prints the files that reach the tests and, in a GitHub Actions step, sets the step's output
`reaches` to `true` or `false`.
"""

import os
import re
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

# The module files that register source engines, and what names a registration in a hunk of
# their diff: its header's enclosing line or a changed line.
ENGINE_MODULES = ("MODULE.bazel", "rules_godot/MODULE.bazel")
_REGISTRATION = re.compile(r"godot_engine|godot_android_shell|^_[A-Z]")

# The tag of the tests that build an engine from source (shared.bazelrc).
_TAG = '"source_engine"'


def _run_git(root: Path, *arguments: str, codes: tuple[int, ...] = (0,)) -> str:
    """Git's output; an exit code outside `codes` fails."""
    result = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode not in codes:
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr
        )
    return result.stdout


def _git(root: Path, *arguments: str, codes: tuple[int, ...] = (0,)) -> list[str]:
    """The NUL-separated paths Git prints."""
    output = _run_git(root, *arguments, codes=codes)
    return [path for path in output.split("\0") if path]


def _covers(path: str, file: str) -> bool:
    """Whether a watched path, a directory with its trailing slash or a file, covers a file."""
    return file.startswith(path) if path.endswith("/") else file == path


def _scope(package: str) -> str:
    """
    What a tagged package's tests read: the whole example for one of an example's packages,
    whose tests build its applications, else the package with its subpackages.
    """
    parts = package.split("/")
    return "/".join(parts[:2]) + "/" if parts[0] == "examples" else package


def watched(root: Path) -> list[str]:
    """The watched paths of the checkout at `root`: the engine paths and the tagged packages."""
    present = _git(root, "ls-files", "-z", "--", *ENGINE_PATHS)
    missing = [p for p in ENGINE_PATHS if not any(_covers(p, f) for f in present)]
    if missing:
        raise FileNotFoundError(
            f"watched paths that no longer exist: {', '.join(missing)}"
        )
    # Exit code 1: no BUILD file names the tag.
    tagged = _git(
        root, "grep", "-l", "-z", "-F", _TAG, "--", "*BUILD.bazel", codes=(0, 1)
    )
    return [*ENGINE_PATHS, *(_scope(path.removesuffix("BUILD.bazel")) for path in tagged)]


def reaching(changed: Iterable[str], paths: Sequence[str]) -> list[str]:
    """The changed files that a watched path covers."""
    return [file for file in changed if any(_covers(path, file) for path in paths)]


def _hunks(diff: str) -> list[tuple[str, list[str]]]:
    """Each hunk of a `git diff -U0`: its header's enclosing line and its changed lines."""
    hunks: list[tuple[str, list[str]]] = []
    for line in diff.splitlines():
        if line.startswith("@@"):
            hunks.append((line.split("@@", 2)[-1].strip(), []))
        # The file headers, `--- a/...` and `+++ b/...`, come before the first hunk.
        elif hunks and line[:1] in ("+", "-"):
            hunks[-1][1].append(line[1:])
    return hunks


def changes_registrations(diff: str) -> bool:
    """
    Whether a `git diff -U0` of module files changes an engine registration: a changed line
    that names one, or an indented one inside a call or constant that its hunk's header names.
    Comments change none.
    """
    for header, lines in _hunks(diff):
        code = [line for line in lines if not line.lstrip().startswith("#")]
        inside = _REGISTRATION.search(header) and any(line[:1].isspace() for line in code)
        if inside or any(_REGISTRATION.search(line) for line in code):
            return True
    return False


def main(argv: list[str]) -> int:
    base, head = argv
    root = Path.cwd()
    # Both sides of a move, so that moving a file out of a watched directory reaches the tests.
    changed = _git(root, "diff", "-z", "--name-only", "--no-renames", f"{base}...{head}")
    found = reaching(changed, watched(root))
    modules = _run_git(root, "diff", "-U0", f"{base}...{head}", "--", *ENGINE_MODULES)
    if changes_registrations(modules):
        found.append("an engine registration in " + " or ".join(ENGINE_MODULES))
    print("\n".join(found) if found else "No change reaches the source-engine tests.")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as file:
            file.write(f"reaches={'true' if found else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
