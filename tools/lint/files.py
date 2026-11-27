"""
The file lint: the linters and formatters of files that have no Bazel targets of their own,
run on files as `aspect format` formats them. It checks the files changed since the merge base
with origin/main, every file Git lists with `--scope=all`, or the files given; `--fix` runs
the formatters instead, which //tools/format runs beside rules_lint's.
`bazel run //tools/lint:files -- [--scope=changed|all] [--fix] [<file>...]`

A tool is a program that takes file paths after its arguments. A linter prints each finding on
a line of its own, `<path>:<line>[:<column>]: <message>`, and exits 1 when it found any, 0
when it found none; any other exit code means it could not check. The tools run at the
repository's root, each once over all of its files, at the same time.

Sections: Tools, Files, Runs, Command line.
"""

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from python.runfiles import runfiles

# ==== Tools ===================================================================

# A shell script's first line, for scripts without a suffix, such as tools/bazel.
_SHELL_SHEBANG = re.compile(r"#!\s*/(usr/)?bin/(env\s+)?(ba)?sh\b")


@dataclass(frozen=True)
class Tool:
    """
    A linter or formatter and the files it takes: those whose name or path matches one of
    `patterns`, with `shebang` also shell scripts without a suffix, but none of `excluded`.
    `check` and `fix` are its arguments before the files in each mode; None leaves it out of
    that mode. `executable` is its path; the repository's tools name the environment variable
    that holds their runfiles path instead (BUILD.bazel).
    """

    name: str
    patterns: tuple[str, ...]
    check: tuple[str, ...] | None = None
    fix: tuple[str, ...] | None = None
    excluded: tuple[str, ...] = ()
    shebang: bool = False
    executable: str = ""

    def _matches(self, path: str, patterns: tuple[str, ...]) -> bool:
        name = path.rsplit("/", 1)[-1]
        return any(
            fnmatch.fnmatchcase(path if "/" in pattern else name, pattern)
            for pattern in patterns
        )

    def _is_script(self, path: str, root: Path) -> bool:
        if not self.shebang or "." in path.rsplit("/", 1)[-1]:
            return False
        with (root / path).open("rb") as file:
            return bool(_SHELL_SHEBANG.match(file.readline().decode(errors="replace")))

    def selected(self, files: Sequence[str], root: Path) -> list[str]:
        """The files of `files`, paths below `root`, that the tool takes."""
        return [
            path
            for path in files
            if not self._matches(path, self.excluded)
            and (self._matches(path, self.patterns) or self._is_script(path, root))
        ]


# The rumdl configuration and its output of one finding per line.
_RUMDL = ("--config", ".rumdl.toml", "--no-cache")

# The repository's tools, each with the variable of its executable's runfiles path.
TOOLS = (
    # GDScript's declaration order (gdscript.py, .gdlintrc).
    Tool("gdlint", ("*.gd",), check=(".gdlintrc",), executable="GDLINT"),
    # Objective-C, which rules_lint's formatter leaves out; //tools/format formats C and C++.
    Tool(
        "clang-format",
        ("*.m", "*.mm"),
        fix=("-i", "--style=file", "--fallback-style=none"),
        executable="CLANG_FORMAT",
    ),
    Tool(
        "rumdl",
        ("*.md",),
        check=("check", *_RUMDL, "--output-format", "concise"),
        fix=("fmt", *_RUMDL, "--quiet"),
        executable="RUMDL",
    ),
    Tool(
        "shellcheck",
        ("*.sh",),
        check=("--format=gcc",),
        shebang=True,
        executable="SHELLCHECK",
    ),
    # The convention rules that judge each file on its own (tools/conventions/files.py); each
    # picks its files from these.
    Tool(
        "conventions",
        (
            "*.md",
            "*.py",
            "*.bzl",
            "BUILD",
            "BUILD.bazel",
            "MODULE.bazel",
            "*.gd",
            "*.cc",
            "*.cpp",
            "*.h",
        ),
        check=("--",),
        executable="CONVENTIONS",
    ),
)


# ==== Files ===================================================================


def _git(root: Path, *arguments: str) -> list[str]:
    output = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    return [line for line in output.split("\0") if line]


def listed_files(root: Path) -> list[str]:
    """Every file Git lists, tracked or untracked and not ignored, but deleted ones."""
    deleted = set(_git(root, "ls-files", "-z", "--deleted"))
    files = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted(set(files) - deleted)


def changed_files(root: Path, base: str) -> list[str]:
    """The files changed since the merge base with `base`, the working tree's included."""
    merge_base = _git(root, "merge-base", "HEAD", base)[0].strip()
    changed = _git(root, "diff", "-z", "--name-only", "--diff-filter=d", merge_base)
    untracked = _git(root, "ls-files", "-z", "--others", "--exclude-standard")
    return sorted(set(changed) | set(untracked))


# ==== Runs ====================================================================

# The longest command line of a batch of files, as rules_lint's formatter keeps it.
_BATCH = 100_000


def _batches(files: list[str]) -> list[list[str]]:
    batches: list[list[str]] = [[]]
    size = 0
    for path in files:
        if batches[-1] and size + len(path) + 1 > _BATCH:
            batches.append([])
            size = 0
        batches[-1].append(path)
        size += len(path) + 1
    return batches


@dataclass(frozen=True)
class _Run:
    """A tool's run in one mode: its arguments, its files and, once it ran, its result."""

    tool: Tool
    arguments: tuple[str, ...]
    files: list[str]
    code: int = 0
    output: str = ""

    def __call__(self, root: Path) -> _Run:
        """Run the tool over its files in batches; keep its worst exit code and its output."""
        code = 0
        output = []
        for batch in _batches(self.files):
            result = subprocess.run(
                [self.tool.executable, *self.arguments, *batch],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            code = max(code, result.returncode)
            output.append(result.stdout)
        return replace(self, code=code, output="".join(output))

    def report(self, fix: bool) -> int:
        """Print what the tool printed unless it passed; 1 for findings, 2 for a failure."""
        if self.code == 0:
            return 0
        found = self.code == 1 and not fix
        if found:
            print(f"{self.tool.name} found problems in {len(self.files)} files:")
        else:
            print(f"{self.tool.name} exited with {self.code}:")
        print(self.output.rstrip())
        return 1 if found else 2


def _runs(tools: Sequence[Tool], files: list[str], root: Path, fix: bool) -> list[_Run]:
    """The runs of the tools of the mode that take any of the files."""
    runs = []
    for tool in tools:
        arguments = tool.fix if fix else tool.check
        if arguments is None:
            continue
        if selected := tool.selected(files, root):
            runs.append(_Run(tool, arguments, selected))
    return runs


def run(
    tools: Sequence[Tool], files: Sequence[str], root: Path, fix: bool = False
) -> int:
    """
    Run each tool of the mode on its files at once and print what those that failed printed.

    Returns 0 when every tool passed, 1 when a linter found something, 2 when a tool could not
    check or fix.
    """
    existing = [path for path in files if (root / path).is_file()]
    runs = _runs(tools, existing, root, fix)
    with ThreadPoolExecutor(max_workers=max(len(runs), 1)) as pool:
        done = list(pool.map(lambda pending: pending(root), runs))
    return max([finished.report(fix) for finished in done], default=0)


# ==== Command line ============================================================


def _executables(tools: Sequence[Tool]) -> tuple[Tool, ...]:
    """The tools with the paths of their executables, from the runfiles their variables name."""
    files = runfiles.Create()
    if files is None:
        raise RuntimeError("the file lint runs with `bazel run //tools/lint:files`")
    return tuple(
        replace(tool, executable=files.Rlocation(os.environ[tool.executable]) or "")
        for tool in tools
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("changed", "all"), default="changed")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--fix", action="store_true", help="Run the formatters")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    tools = _executables(TOOLS)
    root = Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", "."))
    if args.files:
        files = args.files
    elif args.scope == "all" or args.fix:
        files = listed_files(root)
    else:
        files = changed_files(root, args.base_ref)
    return run(tools, files, root, fix=args.fix)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
