"""Code Health of a change, or of the whole checkout, through the CodeScene CLI.

By default it reviews the change: the files changed since the merge base with --base
(origin/main), untracked ones included, scored at both ends. Per file it prints the score
before and after and each new finding with its function and lines, and it exits with 1
when a file declines (change.py). --only reviews just the given files the same way and also
lists the findings they had before. --survey reports the whole checkout instead: languages,
hotspots and the lowest scores (survey.py).

Starlark and GDScript are scored as translated Python (translation.py); the scanner, its
rules and its requirements are described in scan.py.

Usage (from the repository root):
    python3 -m tools.code_health.codescene [REPO] [--base origin/main] [--only PATH ...]
        [--survey [--top 20] [--since 6.months]] [--json out.json]
        [--include-build-files] [--exclude GLOB ...] [--rules code-health-rules.json]
        [--keep-macro-arguments] [--if-available]

--if-available lets the pre-push hook (hk.pkl) pass with a note on a machine without the
CodeScene CLI or token, instead of blocking every push there.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from tools.code_health import change, survey
from tools.code_health.change import ChangedPath, FileChange
from tools.code_health.scan import (
    DEFAULT_EXCLUDES,
    FileResult,
    Scanner,
    Unavailable,
    cli_environment,
    find_cli,
    git,
    in_commit,
    is_selected,
    rules_workspace,
    scan_notes,
    worktree_files,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument(
        "--base",
        default="origin/main",
        help="review the change since the merge base with this ref (default: origin/main)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--only",
        nargs="+",
        metavar="PATH",
        help="review just these repository-relative files against the merge base, "
        "with all their findings",
    )
    mode.add_argument(
        "--survey",
        action="store_true",
        help="report the whole checkout: languages, hotspots and the lowest scores",
    )
    parser.add_argument(
        "--include-build-files",
        action="store_true",
        help="also analyse BUILD/MODULE/WORKSPACE files as Starlark",
    )
    parser.add_argument("--exclude", nargs="*", default=[], help="extra glob excludes")
    parser.add_argument(
        "--since", help="survey: history window for hotspots, e.g. 6.months"
    )
    parser.add_argument("--top", type=int, default=20, help="survey: rows per table")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--json", type=Path, help="write all results as JSON")
    parser.add_argument("--rules", type=Path, help="code-health-rules.json to apply")
    parser.add_argument(
        "--if-available",
        action="store_true",
        help="succeed with a note when the CodeScene CLI or token is missing",
    )
    parser.add_argument(
        "--keep-macro-arguments",
        action="store_true",
        help="count Bazel macro parameters like any function's",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = Path(git(args.repo, "rev-parse", "--show-toplevel").strip())
    try:
        cli, environment = find_cli(), cli_environment()
    except Unavailable as missing:
        if not args.if_available:
            sys.exit(str(missing))
        print(f"code-health: skipped: {missing}", file=sys.stderr)
        sys.exit(0)
    workspace, rules_source = rules_workspace(repo, args.rules)
    scanner = Scanner(
        cli, environment, workspace, args.keep_macro_arguments, repo, args.jobs
    )
    try:
        run = survey_checkout if args.survey else review_change
        status = run(args, scanner, rules_source)
    finally:
        if workspace != repo:
            shutil.rmtree(workspace, ignore_errors=True)
    sys.exit(status)


# --- a change ---------------------------------------------------------------------------


def selected_paths(
    args: argparse.Namespace, paths: list[ChangedPath]
) -> list[ChangedPath]:
    """The changed files to score: each side kept only when it is analysable."""
    excludes = DEFAULT_EXCLUDES + args.exclude

    def kept(path: str | None) -> str | None:
        selected = path and is_selected(path, args.include_build_files, excludes)
        return path if selected else None

    sides = [ChangedPath(kept(p.before), kept(p.after)) for p in paths]
    return [p for p in sides if p.before or p.after]


def only_paths(repo: Path, since: str, paths: list[str]) -> list[ChangedPath]:
    """The given files, at the merge base where they exist and in the working tree."""
    sides = [
        ChangedPath(
            path if in_commit(repo, since, path) else None,
            path if (repo / path).is_file() else None,
        )
        for path in paths
    ]
    missing = [path for path, side in zip(paths, sides, strict=True) if not side.label]
    if missing:
        sys.exit(f"Neither in the working tree nor at {since[:12]}: {', '.join(missing)}")
    return sides


def score_changes(
    scanner: Scanner, since: str, paths: list[ChangedPath]
) -> tuple[list[FileChange], list[FileResult]]:
    """
    Each file's change, and every result, both sides scored in one scan so that neither
    waits for the other's slowest file.
    """
    sides: list[tuple[str | None, str]] = [(since, p.before) for p in paths if p.before]
    sides += [(None, p.after) for p in paths if p.after]
    results = dict(zip(sides, scanner.scan(sides), strict=True))
    changes = [
        FileChange(p, results.get((since, p.before)), results.get((None, p.after)))
        for p in paths
    ]
    return changes, list(results.values())


def review_status(changes: list[FileChange], results: list[FileResult]) -> int:
    """1 when a file declined or could not be scored, else 0."""
    unscored = sorted({r.path for r in results if r.error})
    if unscored:
        print(f"CodeScene could not score: {', '.join(unscored)}", file=sys.stderr)
    return 1 if unscored or any(c.declined for c in changes) else 0


def review_change(args: argparse.Namespace, scanner: Scanner, rules_source: str) -> int:
    since = change.merge_base(scanner.repo, args.base)
    paths = (
        only_paths(scanner.repo, since, args.only)
        if args.only
        else selected_paths(args, change.changed_paths(scanner.repo, since))
    )
    changes, results = score_changes(scanner, since, paths)
    if args.json:
        change.write_json(args.json, args.base, since, changes)
    after = [c.after for c in changes if c.after]
    notes = scan_notes(after, args.keep_macro_arguments, rules_source)
    against = f"`{args.base}` (merge base {since[:12]})"
    print(change.report(changes, against, notes, all_findings=bool(args.only)))
    return review_status(changes, results)


# --- the whole checkout ------------------------------------------------------------------


def survey_checkout(args: argparse.Namespace, scanner: Scanner, rules_source: str) -> int:
    excludes = DEFAULT_EXCLUDES + args.exclude
    files = worktree_files(scanner.repo, args.include_build_files, excludes)
    results = scanner.scan([(None, path) for path in files])
    commits = survey.revisions(scanner.repo, args.since)
    if args.json:
        survey.write_json(args.json, scanner.repo, results, commits)
    notes = scan_notes(results, args.keep_macro_arguments, rules_source)
    print(survey.report(results, commits, args.top, notes))
    return 0


if __name__ == "__main__":
    main()
