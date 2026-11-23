"""Scan a whole Git repository with the CodeScene CLI, including languages it lacks.

The CodeScene CLI (shipped inside the CodeHealth MCP server) reviews one file per
call. This wrapper feeds every file through stdin under a *virtual* file name, so
files CodeScene does not know are analysed as a language it does:

Starlark (.bzl, optionally BUILD/MODULE files) is fed as Python without its
documentation strings, with Bazel macros exempt from the argument count, and GDScript (.gd)
as rewritten Python (translation.py). Line numbers in the findings are mapped back to the
original file.

Nothing in the repository is modified and no mirror is needed; results are
reported under the original paths. With --compare REF the same scan runs on REF
(through `git show`), and the report adds per-file deltas.

Code Health rules: a code-health-rules.json passed with --rules, else the
repository's own .codescene/code-health-rules.json. Its matching_content_path globs
see the virtual names, e.g. "**/*.bzl.py" for Starlark and "**/*.gd.py" for GDScript.

Requirements: the CodeHealth MCP server has run once (it extracts the `cs` CLI
to its cache), and a CodeScene token is configured (CS_ACCESS_TOKEN, or the
access_token the MCP server stores in its config.json). The token is never printed.

Usage (from the repository root, or `python3 -m tools.code_health.codescene ...`):
    python3 -m tools.code_health.codescene [REPO] [--compare main] [--top 20] [--json out.json]
        [--include-build-files] [--exclude GLOB ...] [--since 6.months]
        [--rules code-health-rules.json] [--keep-macro-arguments] [--only PATH ...]
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tools.code_health.translation import (
    MAX_ARGUMENTS,
    NATIVE,
    original_title,
    translate,
)

LANGUAGE = {
    ".py": "Python",
    ".pyi": "Python",
    ".bzl": "Starlark",
    ".gd": "GDScript",
    ".c": "C/C++",
    ".cc": "C/C++",
    ".cpp": "C/C++",
    ".cxx": "C/C++",
    ".h": "C/C++",
    ".hh": "C/C++",
    ".hpp": "C/C++",
    ".hxx": "C/C++",
    ".m": "Objective-C",
    ".mm": "Objective-C",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".dart": "Dart",
    ".go": "Go",
    ".rs": "Rust",
}
BUILD_FILE = re.compile(
    r"(^|/)(BUILD|BUILD\.bazel|MODULE\.bazel|WORKSPACE(\.bazel)?)$|\.star$"
)
DEFAULT_EXCLUDES = [
    "*/third_party/*",
    "*/vendor/*",
    "*/node_modules/*",
]


@dataclass
class FileResult:
    path: str
    language: str
    loc: int
    score: float | None
    smells: list[dict] = field(default_factory=list)
    revisions: int = 0
    macros: list[str] = field(default_factory=list)

    @property
    def priority(self) -> float:
        return self.revisions * (10.0 - self.score) if self.score is not None else 0.0


# --- environment --------------------------------------------------------------


def find_cli() -> str:
    if os.environ.get("CODESCENE_CLI"):
        return os.environ["CODESCENE_CLI"]
    cache = (
        Path.home() / "Library/Caches/codehealth-mcp"
        if platform.system() == "Darwin"
        else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "codehealth-mcp"
    )
    candidates = sorted(glob.glob(str(cache / "MCP-*" / "cs")), key=os.path.getmtime)
    if not candidates:
        sys.exit(
            f"CodeScene CLI not found under {cache}; run the CodeHealth MCP server "
            "once or set CODESCENE_CLI"
        )
    return candidates[-1]


def cli_environment() -> dict[str, str]:
    env = dict(os.environ, CS_DISABLE_VERSION_CHECK="1")
    if not env.get("CS_ACCESS_TOKEN"):
        config = (
            Path.home() / "Library/Application Support/codehealth-mcp/config.json"
            if platform.system() == "Darwin"
            else Path.home() / ".config/codehealth-mcp/config.json"
        )
        try:
            token = json.loads(config.read_text()).get("access_token")
        except OSError, ValueError:
            token = None
        if not token:
            sys.exit(
                "No CodeScene token: set CS_ACCESS_TOKEN or configure the MCP server"
            )
        env["CS_ACCESS_TOKEN"] = token
    return env


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


# --- file selection and translation --------------------------------------------


def listed_paths(repo: Path, ref: str | None) -> list[str]:
    if ref:
        listing = git(repo, "ls-tree", "-r", "--name-only", "-z", ref)
    else:
        listing = git(
            repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard"
        )
    return list(filter(None, listing.split("\0")))


def is_analysable(path: str, include_build: bool) -> bool:
    suffix = Path(path).suffix
    return (
        suffix in NATIVE
        or suffix in (".bzl", ".gd")
        or bool(include_build and BUILD_FILE.search(path))
    )


def is_excluded(path: str, excludes: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in excludes)


def exists_at(repo: Path, ref: str | None, path: str) -> bool:
    """Whether the path is a file at the ref, or in the working tree without one."""
    return bool(ref) or (repo / path).is_file()


def files_at(
    repo: Path, ref: str | None, include_build: bool, excludes: list[str]
) -> list[str]:
    return sorted(
        {
            path
            for path in listed_paths(repo, ref)
            if is_analysable(path, include_build)
            and not is_excluded(path, excludes)
            and exists_at(repo, ref, path)
        }
    )


def language_of(path: str) -> str:
    if BUILD_FILE.search(path):
        return "Starlark (BUILD)"
    return LANGUAGE.get(Path(path).suffix, Path(path).suffix.lstrip(".") or "other")


def loc(source: str) -> int:
    return sum(
        1
        for line in source.splitlines()
        if line.strip() and not line.strip().startswith(("#", "//"))
    )


# --- scanning -------------------------------------------------------------------


@dataclass
class Scanner:
    cli: str
    env: dict[str, str]
    cwd: Path  # a git repository whose .codescene/code-health-rules.json applies
    macro_arguments: bool
    repo: Path
    jobs: int

    def source_of(self, ref: str | None, path: str) -> str:
        if ref:
            return git(self.repo, "show", f"{ref}:{path}")
        return (self.repo / path).read_text(errors="replace")

    def scan(self, ref: str | None, files: list[str]) -> dict[str, FileResult]:
        def one(path: str) -> FileResult:
            return self.review(path, self.source_of(ref, path))

        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            return {r.path: r for r in pool.map(one, files)}

    def review(self, path: str, source: str) -> FileResult:
        translation = translate(path, source, self.macro_arguments)
        result = subprocess.run(
            [
                self.cli,
                "review",
                "--file-name",
                translation.virtual_name,
                "--output-format",
                "json",
            ],
            input=translation.source,
            capture_output=True,
            text=True,
            cwd=self.cwd,
            env=self.env,
            check=False,
        )
        score, smells = None, []
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            score = data.get("score")
            for item in data.get("review", []):
                smells.append(
                    {
                        "category": item["category"],
                        "functions": [
                            {
                                "name": original_title(f.get("title", ""), translation),
                                "start": translation.original_line(f.get("start-line")),
                                "end": translation.original_line(f.get("end-line")),
                                "details": f.get("details", ""),
                            }
                            for f in item.get("functions", [])
                        ],
                    }
                )
        elif result.returncode != 0:
            print(f"warning: {path}: {result.stderr.strip()[:200]}", file=sys.stderr)
        return FileResult(
            path, language_of(path), loc(source), score, smells, macros=translation.macros
        )


def rules_workspace(repo: Path, rules: Path | None) -> tuple[Path, str]:
    """The directory to run the CLI in, so that the chosen rules apply."""
    if rules is None:
        own = repo / ".codescene" / "code-health-rules.json"
        return repo, (
            f"repository's {own.relative_to(repo)}"
            if own.is_file()
            else "CodeScene defaults"
        )
    workspace = Path(tempfile.mkdtemp(prefix="codescene-rules-"))
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    (workspace / ".codescene").mkdir()
    shutil.copy(rules, workspace / ".codescene" / "code-health-rules.json")
    return workspace, str(rules)


def revisions(repo: Path, since: str | None) -> Counter[str]:
    args = ["log", "--no-merges", "--no-renames", "--format=", "--name-only"]
    if since:
        args.append(f"--since={since}")
    return Counter(line for line in git(repo, *args).splitlines() if line)


# --- report -----------------------------------------------------------------------


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


@dataclass
class Comparison:
    """The scan of a reference revision and the files that differ from it."""

    ref: str
    base: dict[str, FileResult]
    changed: set[str]


def summary_section(
    rs: list[FileResult], comparison: Comparison | None, notes: list[str]
) -> list[str]:
    bands = band_counts(rs)
    versus = (
        f" (at `{comparison.ref}`: {weighted(list(comparison.base.values())):.2f})"
        if comparison
        else ""
    )
    return [
        "# CodeScene Code Health report",
        "",
        (
            f"{len(rs)} files analysed, {len(scored(rs))} with scorable code. "
            f"Size-weighted average Code Health: **{weighted(rs):.2f}**{versus}."
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


def hotspot_section(rs: list[FileResult], top: int) -> list[str]:
    hotspots = sorted(
        (r for r in scored(rs) if r.priority > 0), key=lambda r: -r.priority
    )
    return [
        "",
        "## Refactoring targets (hotspots)",
        "",
        "Priority = commits touching the file × (10 − Code Health).",
        "",
        "| File | Commits | LoC | Health | Main findings |",
        "|---|---:|---:|---:|---|",
        *[
            f"| `{r.path}` | {r.revisions} | {r.loc} | {r.score:.2f} | {smell_summary(r)} |"
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


def finding_keys(result: FileResult | None) -> set[tuple[str, str]]:
    """The (category, function) pairs of a file's findings, ignoring line numbers."""
    if result is None:
        return set()
    return {
        (s["category"], f["name"].split(":")[0])
        for s in result.smells
        for f in s["functions"] or [{"name": ""}]
    }


def new_findings(before: FileResult | None, after: FileResult | None) -> list[str]:
    return sorted(
        {category for category, _ in finding_keys(after) - finding_keys(before)}
    )


def score_change(before: float | None, after: float | None) -> tuple[float, str]:
    """The sort key and the label of a file's score change."""
    if before is None:
        return 0, "new"
    if after is None:
        return 0, "deleted"
    return after - before, f"{after - before:+.2f}"


def change_row(
    path: str, before: FileResult | None, after: FileResult | None
) -> tuple[float, str] | None:
    old = before.score if before else None
    new = after.score if after else None
    if old is None and new is None:
        return None
    key, label = score_change(old, new)
    cell = lambda v: "–" if v is None else f"{v:.2f}"
    return key, (
        f"| `{path}` | {cell(old)} | {cell(new)} | {label} | "
        f"{', '.join(new_findings(before, after))} |"
    )


def changes_section(results: dict[str, FileResult], comparison: Comparison) -> list[str]:
    rows = [
        change_row(path, comparison.base.get(path), results.get(path))
        for path in sorted(comparison.changed)
    ]
    return [
        "",
        f"## Changes against `{comparison.ref}`",
        "",
        "| File | Before | After | Δ | New findings |",
        "|---|---:|---:|---:|---|",
        *[line for _, line in sorted(filter(None, rows), key=lambda row: row[0])],
    ]


def report(
    results: dict[str, FileResult],
    comparison: Comparison | None,
    top: int,
    notes: list[str],
) -> str:
    rs = list(results.values())
    out = [
        *summary_section(rs, comparison, notes),
        *language_section(rs),
        *hotspot_section(rs, top),
        *lowest_section(rs, top),
        *findings_section(rs),
    ]
    if comparison is not None:
        out += changes_section(results, comparison)
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument(
        "--compare", metavar="REF", help="also scan REF and report deltas"
    )
    parser.add_argument(
        "--include-build-files",
        action="store_true",
        help="also analyse BUILD/MODULE/WORKSPACE files as Starlark",
    )
    parser.add_argument("--exclude", nargs="*", default=[], help="extra glob excludes")
    parser.add_argument("--since", help="history window for hotspots, e.g. 6.months")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--json", type=Path, help="write all results as JSON")
    parser.add_argument("--rules", type=Path, help="code-health-rules.json to apply")
    parser.add_argument(
        "--keep-macro-arguments",
        action="store_true",
        help="count Bazel macro parameters like any function's",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="PATH",
        help="review just these repository-relative files and print every "
        "finding with its lines (like code_health_review)",
    )
    args = parser.parse_args()

    repo = Path(git(args.repo, "rev-parse", "--show-toplevel").strip())
    workspace, rules_source = rules_workspace(repo, args.rules)
    scanner = Scanner(
        find_cli(),
        cli_environment(),
        workspace,
        args.keep_macro_arguments,
        repo,
        args.jobs,
    )
    try:
        run(args, scanner, rules_source)
    finally:
        if workspace != repo:
            shutil.rmtree(workspace, ignore_errors=True)


def function_line(f: dict) -> str:
    where = f"lines {f['start']}-{f['end']}" if f["start"] else "file"
    return f"  - `{f['name']}` ({where}): {f['details']}"


def smell_lines(smell: dict) -> list[str]:
    return [f"- {smell['category']}", *map(function_line, smell["functions"])]


def result_lines(r: FileResult) -> list[str]:
    score = "no scorable code" if r.score is None else f"{r.score:.2f}"
    lines = [f"## {r.path}: Code Health {score}", ""]
    if r.macros:
        lines.append(
            f"Bazel macros exempt from the argument count: {', '.join(r.macros)}"
        )
    for smell in r.smells:
        lines += smell_lines(smell)
    return [*lines, ""]


def details(results: dict[str, FileResult]) -> str:
    return "\n".join(line for r in results.values() for line in result_lines(r))


def count_revisions(
    results: dict[str, FileResult], repo: Path, since: str | None
) -> None:
    for path, n in revisions(repo, since).items():
        if path in results:
            results[path].revisions = n


def compare_with(
    scanner: Scanner, ref: str, files: list[str], results: dict[str, FileResult]
) -> Comparison:
    base = scanner.scan(ref, files)
    changed = set(git(scanner.repo, "diff", "--name-only", ref, "--").split())
    changed |= set(
        git(scanner.repo, "ls-files", "--others", "--exclude-standard").split()
    )
    return Comparison(ref, base, changed & (set(results) | set(base)))


def write_json(
    path: Path, repo: Path, results: dict[str, FileResult], comparison: Comparison | None
) -> None:
    payload: dict = {
        "repository": str(repo),
        "files": [asdict(r) | {"priority": r.priority} for r in results.values()],
    }
    if comparison is not None:
        payload["compare"] = {
            "ref": comparison.ref,
            "files": [asdict(r) for r in comparison.base.values()],
        }
    path.write_text(json.dumps(payload, indent=2))


def report_notes(
    results: dict[str, FileResult], keep_macro_arguments: bool, rules_source: str
) -> list[str]:
    macros = sum(len(r.macros) for r in results.values())
    return [
        f"Code Health rules: {rules_source}.",
        "Bazel macro parameters counted like any function's."
        if keep_macro_arguments
        else f"{macros} Bazel macros with more than {MAX_ARGUMENTS} parameters exempt from "
        "Excess Number of Function Arguments: their parameters mirror rule attributes, "
        "which CodeScene does not count either.",
    ]


def run(args: argparse.Namespace, scanner: Scanner, rules_source: str) -> None:
    if args.only:
        print(details(scanner.scan(None, args.only)))
        return
    excludes = DEFAULT_EXCLUDES + args.exclude

    def files(ref: str | None) -> list[str]:
        return files_at(scanner.repo, ref, args.include_build_files, excludes)

    results = scanner.scan(None, files(None))
    count_revisions(results, scanner.repo, args.since)
    comparison = (
        compare_with(scanner, args.compare, files(args.compare), results)
        if args.compare
        else None
    )
    if args.json:
        write_json(args.json, scanner.repo, results, comparison)
    notes = report_notes(results, args.keep_macro_arguments, rules_source)
    print(report(results, comparison, args.top, notes))


if __name__ == "__main__":
    main()
