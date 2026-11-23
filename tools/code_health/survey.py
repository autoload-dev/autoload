"""The Code Health of a whole checkout: languages, hotspots and the lowest scores."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from tools.code_health.scan import FileResult, git


def revisions(repo: Path, since: str | None) -> Counter[str]:
    args = ["log", "--no-merges", "--no-renames", "--format=", "--name-only"]
    if since:
        args.append(f"--since={since}")
    return Counter(line for line in git(repo, *args).splitlines() if line)


def weighted(results: list[FileResult]) -> float:
    weights = [(r.score, r.loc) for r in results if r.score is not None and r.loc]
    total = sum(weight for _, weight in weights) or 1
    return sum(score * weight for score, weight in weights) / total


def band(score: float) -> str:
    return "green" if score >= 9 else "yellow" if score >= 4 else "red"


def band_counts(results: list[FileResult]) -> Counter[str]:
    return Counter(band(r.score) for r in results if r.score is not None)


def scored(results: list[FileResult]) -> list[FileResult]:
    return [r for r in results if r.score is not None]


def category_counts(results: list[FileResult]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for r in results:
        for s in r.smells:
            counts[s["category"]] += max(1, len(s["functions"]))
    return counts


def smell_summary(r: FileResult, limit: int = 3) -> str:
    most_common = category_counts([r]).most_common(limit)
    return ", ".join(f"{k} ×{n}" if n > 1 else k for k, n in most_common)


def summary_section(rs: list[FileResult], notes: list[str]) -> list[str]:
    bands = band_counts(rs)
    return [
        "# CodeScene Code Health report",
        "",
        (
            f"{len(rs)} files analysed, {len(scored(rs))} with scorable code. "
            f"Size-weighted average Code Health: **{weighted(rs):.2f}**."
        ),
        (
            f"Green (≥ 9): {bands['green']}, yellow (4–8.9): {bands['yellow']}, "
            f"red (< 4): {bands['red']}."
        ),
        "",
        (
            "Starlark is analysed as Python and GDScript as rewritten Python; CodeScene "
            "then applies Python thresholds (e.g. at most 4 function arguments)."
        ),
        *[f"- {note}" for note in notes],
        "",
    ]


def language_row(language: str, items: list[FileResult]) -> str:
    bands = band_counts(items)
    return (
        f"| {language} | {len(items)} | {len(scored(items))} | {sum(r.loc for r in items)} | "
        f"{weighted(items):.2f} | {bands['red']} | {bands['yellow']} |"
    )


def language_section(rs: list[FileResult]) -> list[str]:
    by_language: defaultdict[str, list[FileResult]] = defaultdict(list)
    for r in rs:
        by_language[r.language].append(r)
    largest_first = sorted(by_language.items(), key=lambda kv: -sum(r.loc for r in kv[1]))
    return [
        "## By language",
        "",
        "| Language | Files | Scored | LoC | Avg health | Red | Yellow |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *[language_row(language, items) for language, items in largest_first],
    ]


def priority(r: FileResult, commits: Counter[str]) -> float:
    """How much refactoring a file pays: commits touching it × (10 − Code Health)."""
    return commits[r.path] * (10.0 - r.score) if r.score is not None else 0.0


def hotspot_section(rs: list[FileResult], commits: Counter[str], top: int) -> list[str]:
    ranked = sorted(scored(rs), key=lambda r: -priority(r, commits))
    hotspots = [r for r in ranked if priority(r, commits) > 0]
    return [
        "",
        "## Refactoring targets (hotspots)",
        "",
        "Priority = commits touching the file × (10 − Code Health).",
        "",
        "| File | Commits | LoC | Health | Main findings |",
        "|---|---:|---:|---:|---|",
        *[
            f"| `{r.path}` | {commits[r.path]} | {r.loc} | {r.score:.2f} | "
            f"{smell_summary(r)} |"
            for r in hotspots[:top]
        ],
    ]


def lowest_section(rs: list[FileResult], top: int) -> list[str]:
    lowest = sorted(scored(rs), key=lambda r: (r.score, -r.loc))
    return [
        "",
        "## Lowest Code Health",
        "",
        "| File | Health | LoC | Main findings |",
        "|---|---:|---:|---|",
        *[
            f"| `{r.path}` | {r.score:.2f} | {r.loc} | {smell_summary(r)} |"
            for r in lowest[:top]
        ],
    ]


def findings_section(rs: list[FileResult]) -> list[str]:
    return [
        "",
        "## Findings across the codebase",
        "",
        *[f"- {c}: {n}" for c, n in category_counts(rs).most_common()],
    ]


def report(
    rs: list[FileResult], commits: Counter[str], top: int, notes: list[str]
) -> str:
    return "\n".join(
        [
            *summary_section(rs, notes),
            *language_section(rs),
            *hotspot_section(rs, commits, top),
            *lowest_section(rs, top),
            *findings_section(rs),
        ]
    )


def write_json(
    path: Path, repo: Path, rs: list[FileResult], commits: Counter[str]
) -> None:
    files = [
        asdict(r) | {"commits": commits[r.path], "priority": priority(r, commits)}
        for r in rs
    ]
    path.write_text(json.dumps({"repository": str(repo), "files": files}, indent=2))
