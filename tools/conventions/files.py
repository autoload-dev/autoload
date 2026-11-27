"""
The convention rules that judge each file on its own, run on given files by their paths in the
repository, from its root, as the file lint runs them (tools/lint/files.py):
`files.py [--rule <name>]... -- <file>...`, every such rule unless named.
"""

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

from tools.conventions.context import (
    Call,
    Context,
    EvidenceError,
    Fact,
    Module,
    Target,
    Workspace,
)
from tools.conventions.framework import Report, Rule, run
from tools.conventions.per_file import RULES


class NoEvidence:
    """The tools that the per-file rules never use: they read files only."""

    @staticmethod
    def _refuse(evidence: str) -> NoReturn:
        raise EvidenceError(
            f"a per-file rule asked for {evidence}, which only the tool loads"
        )

    def calls(self, module: Module) -> tuple[Call, ...]:
        self._refuse("parsed calls")

    def module_name(self, module: Module) -> str:
        self._refuse("module names")

    def rules(self, module: Module) -> tuple[Target, ...]:
        self._refuse("evaluated rules")

    def inspect(self, module: Module, labels: tuple[str, ...]) -> Mapping[str, Fact]:
        self._refuse("label facts")

    def invocations(self, module: Module) -> Mapping[str, tuple[tuple[str, str], ...]]:
        self._refuse("instantiation stacks")

    def dependent_tests(
        self, module: Module, labels: tuple[str, ...], excluded_tags: tuple[str, ...]
    ) -> frozenset[str]:
        self._refuse("dependent tests")


def selected(ids: list[str] | None) -> tuple[Rule, ...]:
    """The per-file rules of the IDs, or all of them."""
    rules = tuple(rule for rule in RULES if ids is None or rule.info.id in ids)
    if ids and len(rules) != len(set(ids)):
        raise EvidenceError("only rules that judge each file on its own run per file")
    return rules


def check(ids: list[str] | None, files: list[str]) -> Report:
    """The rules' report on the files, by their paths below the current directory."""
    sources = {file: Path(file) for file in files}
    workspace = Workspace(Path.cwd(), tuple(sources), sources)
    return run(Context(workspace, NoEvidence(), NoEvidence()), selected(ids))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rule", action="append", help="Run only this rule; repeatable")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    try:
        report = check(args.rule, args.files)
    except ValueError as error:
        print(f"Convention check could not complete: {error}")
        return 2
    for diagnostic in report.diagnostics:
        print(diagnostic)
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
