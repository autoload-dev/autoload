"""
The files changed since the merge base with a reference, which the pre-push hook's work
selects its steps by (tools/ci/work.py). A push counts from the pushed branch's commit on the
remote, which the hook checked when it was pushed, as long as HEAD descends from it; a
branch's first push, and one that rewrites history the remote has not seen, count from the
merge base with origin/main (pushed_base).

The changes are the working tree's against the merge base: committed, staged and unstaged
edits, deletions and untracked files. A change to the verification tooling itself selects
every step, so a broken selection cannot hide itself.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from tools.code_health.change import changed_paths
from tools.code_health.scan import run_git

# The tooling that runs and selects the work; `*` matches across directories.
SELECTS_EVERYTHING = (
    "tools/ci/*",
    ".aspect/*",
    "*.bazelrc",
    ".bazelversion",
    "tools/bazel",
    "*/tools/bazel",
    # What the selection itself reads: the change and the modules.
    "tools/code_health/change.py",
    "tools/code_health/scan.py",
    "tools/setup/modules.py",
)


def matches(path: str, patterns: Iterable[str]) -> bool:
    """Whether a path matches one of the patterns, whose `*` matches across directories."""
    return any(fnmatchcase(path, pattern) for pattern in patterns)


@dataclass(frozen=True)
class Changes:
    """The changed paths since a merge base, by its short name, and the checkout's modules."""

    paths: frozenset[str]
    base: str
    modules: tuple[str, ...]

    def touch(self, patterns: Iterable[str]) -> bool:
        """Whether a changed path matches one of the patterns."""
        patterns = tuple(patterns)
        return any(matches(path, patterns) for path in self.paths)

    def owner(self, path: str) -> str:
        """The innermost module a path lies in."""
        holding = (m for m in self.modules if m == "." or path.startswith(f"{m}/"))
        return max(holding, key=len)

    def in_module(self, module: str, names: Iterable[str]) -> bool:
        """
        Whether a changed path whose file name matches one of the patterns lies in the
        module and none of the modules nested in it.
        """
        names = tuple(names)
        return any(
            self.owner(path) == module and matches(Path(path).name, names)
            for path in self.paths
        )


# Whether a step's inputs changed, given the changes and the directory the step runs in.
Inputs = Callable[[Changes, str], bool]


def files(*patterns: str) -> Inputs:
    """Inputs of the paths that match the patterns."""
    return lambda changes, _: changes.touch(patterns)


def module_files(*names: str) -> Inputs:
    """Inputs of the module a step runs in: its files whose names match the patterns."""
    return lambda changes, directory: changes.in_module(directory, names)


def either(*inputs: Inputs) -> Inputs:
    """Inputs of each of the given inputs."""
    return lambda changes, directory: any(i(changes, directory) for i in inputs)


def pushed_base(ref: str, remote_tips: Iterable[str], root: Path) -> str:
    """
    The reference a push counts its changes from: the pushed branches' commit on the
    remote, when they share one that HEAD descends from, else `ref`, with the reason
    printed. A remote tip of zeros stands for a branch the remote does not have yet.
    """
    tips = set(remote_tips)
    if any(set(tip) == {"0"} for tip in tips):
        return fallback(ref, "the remote has no such branch")
    if len(tips) > 1:
        return fallback(ref, "several pushed branches are on different commits")
    (tip,) = tips
    if run_git(root, "merge-base", "--is-ancestor", tip, "HEAD").returncode:
        return fallback(ref, f"the remote's {tip[:9]} is not in HEAD's history")
    print(f"[work] counting changes since the remote's {tip[:9]}", flush=True)
    return tip


def fallback(ref: str, reason: str) -> str:
    """The reference itself, with the reason a push counts from its merge base printed."""
    print(
        f"[work] {reason}: counting changes since the merge base with {ref}", flush=True
    )
    return ref


def changes_since(ref: str, root: Path, modules: tuple[str, ...]) -> Changes | None:
    """
    The changes since the merge base of HEAD and a reference, or none, with the reason
    printed, when every step must run: without a merge base, or after a change to the
    verification tooling. A rename changes both paths.
    """
    merge_base = run_git(root, "merge-base", "HEAD", ref)
    if merge_base.returncode != 0:
        reason = merge_base.stderr.strip().splitlines()[-1:] or ["unrelated histories"]
        print(f"[work] no merge base with {ref} ({reason[0]}): running every step")
        return None
    base = merge_base.stdout.strip()
    paths = frozenset(
        path
        for change in changed_paths(root, base)
        for path in (change.before, change.after)
        if path
    )
    if tooling := sorted(p for p in paths if matches(p, SELECTS_EVERYTHING)):
        print(f"[work] {tooling[0]} changed: running every step", flush=True)
        return None
    return Changes(paths, base[:9], modules)
