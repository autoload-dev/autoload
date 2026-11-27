"""
The change history of files: how often each changed, with which files it changed, and how
often each of its regions changed. It informs the code-health skill which files deserve a
thorough review and where a file's boundaries lie (docs/internal/code-health.md).

Usage (from the repository root), through `aspect code-health --history -- <options>`:
    python3 -m tools.code_health.history [REPO] [--base origin/main] [--since 6.months]
        [--only PATH ...]

Without --only it reports the files changed since the merge base with --base. Git follows
renames, so a moved file keeps its history.

Sections: History, Report.
"""

from __future__ import annotations

import argparse
import bisect
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from tools.code_health import change
from tools.code_health.scan import git, run_git

# A region header, as region-headers-named-in-head requires it
# (tools/conventions/rules/region_headers_named_in_head.py).
REGION = re.compile(r"(?:#|//) ==== (?P<name>[^=\s](?:[^=]*[^=\s])?) =+$")
# A hunk header of a unified diff with no context: the changed lines of the new version.
HUNK = re.compile(
    r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@", re.MULTILINE
)
# How many files that changed with a file the report names.
PARTNERS = 5


# ==== History =================================================================


@dataclass(frozen=True)
class Commit:
    """
    A commit that touched a file: the file's path in it and in the commit before, if the
    file existed then, and the files the commit touched.
    """

    sha: str
    path: str
    previous: str | None
    files: frozenset[str]


def log_files(repo: Path, since: str | None, *args: str) -> list[tuple[str, list[str]]]:
    """Each commit of a `git log` and the files it names, newest first."""
    window = [f"--since={since}"] if since else []
    log = git(
        repo, "log", "--no-merges", *window, "--format=commit %H", "--name-only", *args
    )
    found: list[tuple[str, list[str]]] = []
    for line in log.splitlines():
        if line.startswith("commit "):
            found.append((line.removeprefix("commit "), []))
        elif line and found:
            found[-1][1].append(line)
    return found


def touched(repo: Path, since: str | None) -> dict[str, frozenset[str]]:
    """The files each commit in the window touched, from one log of the repository."""
    return {
        sha: frozenset(files) for sha, files in log_files(repo, since, "--no-renames")
    }


def commits(
    repo: Path, path: str, since: str | None, files: dict[str, frozenset[str]]
) -> list[Commit]:
    """The commits that touched a file, newest first, following its renames."""
    logged = log_files(repo, since, "--follow", "--", path)
    found = [(sha, names[-1]) for sha, names in logged if names]
    previous = [name for _, name in found[1:]] + [None]
    return [
        Commit(sha, name, before, files.get(sha, frozenset()))
        for (sha, name), before in zip(found, previous)
    ]


def regions(text: str) -> list[tuple[int, str]]:
    """The region headers of a file, by line."""
    return [
        (number, found["name"])
        for number, line in enumerate(text.splitlines(), 1)
        if (found := REGION.fullmatch(line))
    ]


def region_of(line: int, headers: list[tuple[int, str]]) -> str | None:
    """The region a line lies in, or None above the first region header."""
    index = bisect.bisect_right([start for start, _ in headers], line)
    return headers[index - 1][1] if index else None


def diff_of(repo: Path, commit: Commit) -> str:
    """The commit's changes of the file, against its path before so a rename is no new file."""
    if commit.previous is not None:
        compared = run_git(
            repo,
            "diff",
            "-U0",
            f"{commit.sha}^:{commit.previous}",
            f"{commit.sha}:{commit.path}",
        )
        if compared.returncode == 0:
            return compared.stdout
    return git(repo, "show", "--format=", "-U0", commit.sha, "--", commit.path)


def regions_in(diff: str, headers: list[tuple[int, str]]) -> set[str]:
    """The regions whose lines a diff changes; a deletion counts where it happened."""
    lines = [
        line
        for hunk in HUNK.finditer(diff)
        for start in [int(hunk["start"])]
        for line in range(start, start + max(int(hunk["count"] or 1), 1))
    ]
    return {name for line in lines if (name := region_of(line, headers)) is not None}


def changed_regions(repo: Path, commit: Commit) -> set[str]:
    """The regions of the file whose lines a commit changed, in the commit's version."""
    shown = run_git(repo, "show", f"{commit.sha}:{commit.path}")
    headers = regions(shown.stdout) if shown.returncode == 0 else []
    return regions_in(diff_of(repo, commit), headers) if headers else set()


@dataclass
class History:
    """A file's history in the window."""

    path: str
    commits: int = 0
    partners: list[tuple[str, int]] = field(default_factory=list)
    together: list[tuple[list[str], int]] = field(default_factory=list)


def history(
    repo: Path, path: str, since: str | None, files: dict[str, frozenset[str]]
) -> History:
    """How often a file changed, with which files, and which of its regions together."""
    found = commits(repo, path, since, files)
    partners: Counter[str] = Counter()
    together: Counter[tuple[str, ...]] = Counter()
    # A file without region headers now has no regions to count in its past.
    has_regions = bool(regions((repo / path).read_text(errors="replace")))
    for commit in found:
        partners.update(
            f for f in commit.files if f not in {commit.path, commit.previous}
        )
        names = changed_regions(repo, commit) if has_regions else set()
        if names:
            together[tuple(sorted(names))] += 1
    return History(
        path,
        len(found),
        partners.most_common(PARTNERS),
        [(list(names), n) for names, n in together.most_common()],
    )


# ==== Report ==================================================================


def report(histories: list[History], since: str | None) -> str:
    """The histories as Markdown, the most often changed file first."""
    window = f"since {since}" if since else "in the whole history"
    lines = [f"# Change history, {window}", ""]
    for item in sorted(histories, key=lambda h: (-h.commits, h.path)):
        lines += [f"## `{item.path}`: {item.commits} commits", ""]
        if item.partners:
            pairs = ", ".join(f"`{p}` ({n})" for p, n in item.partners)
            lines += [f"Changed most often with: {pairs}.", ""]
        if item.together:
            lines += ["| Regions changed together | Commits |", "|---|---:|"]
            lines += [f"| {', '.join(names)} | {n} |" for names, n in item.together]
            lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument(
        "--base", default="origin/main", help="report the change since its merge base"
    )
    parser.add_argument(
        "--since", default="6.months", help="history window; 'all' for all"
    )
    parser.add_argument("--only", nargs="+", metavar="PATH", help="report these files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = args.repo.resolve()
    since = None if args.since == "all" else args.since
    if args.only:
        paths = args.only
    else:
        base = change.merge_base(repo, args.base)
        paths = [c.after for c in change.changed_paths(repo, base) if c.after]
    files = touched(repo, since)
    histories = [
        history(repo, path, since, files) for path in paths if (repo / path).is_file()
    ]
    print(report(histories, since))


if __name__ == "__main__":
    sys.exit(main())
