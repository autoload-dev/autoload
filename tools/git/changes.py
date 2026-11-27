"""
The files a change touches, for the tools that review a change: the working tree against a
commit, untracked files included (changed_paths), or the index against HEAD (staged_paths).
A branch's change starts at its merge base with a base ref (merge_base), so that commits
which landed on the base after the branch point are not part of it.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@dataclass(frozen=True)
class ChangedPath:
    """A file of a change: its path before and after it."""

    before: str | None  # None for a file the change adds
    after: str | None  # None for a file the change deletes

    @property
    def label(self) -> str:
        """The path, or `old → new` for a renamed file."""
        return " → ".join(dict.fromkeys(p for p in (self.before, self.after) if p))


def parse_name_status(output: str) -> list[ChangedPath]:
    """The files of `git diff --name-status -z -M` output, renames as one file."""
    fields = output.split("\0")
    paths: list[ChangedPath] = []
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index][0]
        if status in "RC":
            old, new = fields[index + 1], fields[index + 2]
            paths.append(ChangedPath(old if status == "R" else None, new))
            index += 3
            continue
        path = fields[index + 1]
        paths.append(
            ChangedPath(None if status == "A" else path, None if status == "D" else path)
        )
        index += 2
    return paths


def merge_base(repo: Path, base: str) -> str | None:
    """The merge base of HEAD with `base`, or None when they have none."""
    try:
        return _git(repo, "merge-base", base, "HEAD").strip()
    except subprocess.CalledProcessError:
        return None


def changed_paths(repo: Path, since: str) -> list[ChangedPath]:
    """The files that differ between the commit and the working tree, untracked included."""
    paths = parse_name_status(_git(repo, "diff", "--name-status", "-z", "-M", since))
    untracked = _git(repo, "ls-files", "-z", "--others", "--exclude-standard")
    paths += [ChangedPath(None, path) for path in untracked.split("\0") if path]
    return paths


def staged_paths(repo: Path) -> list[ChangedPath]:
    """The files the index changes against HEAD."""
    return parse_name_status(
        _git(repo, "diff", "--cached", "--name-status", "-z", "-M", "HEAD")
    )
