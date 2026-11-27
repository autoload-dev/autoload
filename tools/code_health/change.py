"""The Code Health of a change: the files it touches, before and after, and which got worse.

A change is either the working tree against its merge base with a base ref or the index
against HEAD (tools/git/changes.py).
A file declines when its score falls, or, for a file without a score before, such as a new
one, when it scores below NEW_FILE_MINIMUM. Deleted files never decline.

Sections: Changed files, Report.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from functools import cached_property
from pathlib import Path

from tools.code_health.scan import BUILD_FILE, FileResult
from tools.git import changes
from tools.git.changes import ChangedPath

NEW_FILE_MINIMUM = 9.0
NO_FUNCTION = {"name": "", "start": None, "end": None, "details": ""}
# Languages whose comments start with `#`; CodeScene reads its directives from comments.
HASH_COMMENT = {
    ".bzl",
    ".ex",
    ".exs",
    ".gd",
    ".pl",
    ".pm",
    ".ps1",
    ".psd1",
    ".psm1",
    ".py",
    ".pyi",
    ".rb",
    ".tcl",
}
ACCEPT_HINT = (
    "Refactor each declined file until it no longer declines. To accept a finding "
    "deliberately instead, put the directive shown under it above its function's definition, "
    'with a comment that gives the reason (docs/internal/code-health.md, "The hooks").'
)


# ==== Changed files ===========================================================


def merge_base(repo: Path, base: str) -> str:
    """The merge base of HEAD with `base`; exit when they have none."""
    since = changes.merge_base(repo, base)
    if since is None:
        sys.exit(f"HEAD has no merge base with {base}, or {base} names no commit.")
    return since


def function_name(function: dict) -> str:
    """A finding's function, without the line its title may carry."""
    return function["name"].split(":")[0]


def findings(result: FileResult | None) -> list[tuple[str, dict]]:
    """Each finding of a file as its category and function; file-level ones without one."""
    if result is None:
        return []
    return [
        (smell["category"], function)
        for smell in result.smells
        for function in smell["functions"] or [NO_FUNCTION]
    ]


def finding_keys(result: FileResult | None) -> set[tuple[str, str]]:
    """The (category, function) pairs of a file's findings, ignoring line numbers."""
    return {(category, function_name(f)) for category, f in findings(result)}


@dataclass
class FileChange:
    path: ChangedPath
    before: FileResult | None
    after: FileResult | None

    @property
    def scores(self) -> tuple[float | None, float | None]:
        return (
            self.before.score if self.before else None,
            self.after.score if self.after else None,
        )

    @property
    def declined(self) -> bool:
        before, after = self.scores
        if after is None:
            return False
        if before is None:
            return after < NEW_FILE_MINIMUM
        return after < before

    @property
    def delta(self) -> float:
        before, after = self.scores
        return 0.0 if before is None or after is None else after - before

    @cached_property
    def new_findings(self) -> list[tuple[str, dict]]:
        """The findings after the change whose category and function had none before."""
        known = finding_keys(self.before)
        return [
            (category, function)
            for category, function in findings(self.after)
            if (category, function_name(function)) not in known
        ]


# ==== Report ==================================================================


def score_cell(score: float | None) -> str:
    return "–" if score is None else f"{score:.2f}"


def delta_cell(change: FileChange) -> str:
    before, after = change.scores
    if change.after is None:
        return "deleted"
    if before is None:
        return "new"
    return "–" if after is None else f"{change.delta:+.2f}"


def function_line(category: str, function: dict) -> str:
    if function["start"]:
        where = f"`{function['name']}`, lines {function['start']}-{function['end']}"
    else:
        where = "file"
    details = f": {function['details']}" if function["details"] else ""
    return f"- {category} ({where}){details}"


def directive(path: str, category: str) -> str:
    """The comment that makes CodeScene accept a finding of the category in the file."""
    hash_comment = Path(path).suffix in HASH_COMMENT or BUILD_FILE.search(path)
    return f'{"#" if hash_comment else "//"} @codescene(disable:"{category}")'


def acceptance_lines(change: FileChange) -> list[str]:
    """For a declined file, the directive that accepts each new finding of a function."""
    located = [(c, f) for c, f in change.new_findings if f["start"]]
    if not change.declined or not located:
        return []
    path = change.path.after or ""
    accepted = dict.fromkeys((directive(path, c), function_name(f)) for c, f in located)
    return [
        "",
        "Directives that accept them, stacked on the lines above each function's definition:",
        "",
        *[f"- `{comment}` above `{function}`" for comment, function in accepted],
    ]


def file_section(change: FileChange, all_findings: bool) -> list[str]:
    before, after = change.scores
    verdict = " — **declined**" if change.declined else ""
    lines = [
        "",
        f"### {change.path.label}: {score_cell(before)} → {score_cell(after)}{verdict}",
        "",
    ]
    new = change.new_findings
    lines += [function_line(c, f) for c, f in new] or ["No new findings."]
    lines += acceptance_lines(change)
    if all_findings:
        known = [(c, f) for c, f in findings(change.after) if (c, f) not in new]
        if known:
            lines += ["", "Findings it had before:", ""]
            lines += [function_line(c, f) for c, f in known]
    return lines


def ordered(changes: list[FileChange]) -> list[FileChange]:
    """Declined files first, then by score change, worst first."""
    return sorted(changes, key=lambda c: (not c.declined, c.delta, c.path.label))


def table(changes: list[FileChange]) -> list[str]:
    if not changes:
        return []
    return [
        "",
        "| File | Before | After | Δ |",
        "|---|---:|---:|---:|",
        *[
            f"| `{c.path.label}` | {score_cell(c.scores[0])} | "
            f"{score_cell(c.scores[1])} | {delta_cell(c)} |"
            for c in changes
        ],
    ]


def has_findings_to_show(change: FileChange, all_findings: bool) -> bool:
    return bool(findings(change.after) if all_findings else change.new_findings)


def report(
    changes: list[FileChange],
    against: str,
    notes: list[str],
    all_findings: bool,
) -> str:
    changes = ordered(changes)
    declined = sum(c.declined for c in changes)
    out = [
        f"# Code Health of the change against {against}",
        "",
        (
            f"Changed files scored: {len(changes)}; declined: {declined or 'none'}. "
            "A file declines when its score falls, or, new, when it scores below "
            f"{NEW_FILE_MINIMUM:.1f}."
        ),
        *[f"- {note}" for note in notes],
        *table(changes),
    ]
    for change in changes:
        if has_findings_to_show(change, all_findings):
            out += file_section(change, all_findings)
    if declined:
        out += ["", ACCEPT_HINT]
    return "\n".join(out)


def write_json(path: Path, against: str, before: str, changes: list[FileChange]) -> None:
    payload = {
        "against": against,
        "before": before,
        "files": [
            {
                "before_path": c.path.before,
                "after_path": c.path.after,
                "before": asdict(c.before) if c.before else None,
                "after": asdict(c.after) if c.after else None,
                "declined": c.declined,
            }
            for c in ordered(changes)
        ],
    }
    path.write_text(json.dumps(payload, indent=2))
