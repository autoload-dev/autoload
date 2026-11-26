"""
The convention rules that judge each file on its own, run on given files, as the lint check's
aspects run them per package (tools/lint/linters.bzl):
`files.py --module-file <MODULE.bazel> [--rule <ID>]... -- <file>...`, every such rule unless
named.

A file is named by its path in the repository: below the directory of the main repository's
module, which its MODULE.bazel names, or below the directory of the add-on module whose
repository holds it.
"""

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
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
from tools.setup.modules import declared_name, module_directory


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


def module_file_directory(module_file: Path) -> str:
    """The directory of the module whose MODULE.bazel is given."""
    name = declared_name(module_file.read_text())
    if not name:
        raise EvidenceError(f"{module_file}: names no module")
    directory = module_directory(name).as_posix()
    return "" if directory == "." else directory


def repository_path(path: str, module: str) -> str:
    """A source's path in the repository, from its path in Bazel's execution root."""
    parts = PurePosixPath(path).parts
    if parts and parts[0] == "external":
        directory = module_directory(parts[1].removesuffix("+"))
        return PurePosixPath(directory, *parts[2:]).as_posix()
    return PurePosixPath(module, path).as_posix() if module else path


def selected(ids: list[str] | None) -> tuple[Rule, ...]:
    """The per-file rules of the IDs, or all of them."""
    rules = tuple(rule for rule in RULES if ids is None or rule.info.id in ids)
    if ids and len(rules) != len(set(ids)):
        raise EvidenceError("only rules that judge each file on its own run per file")
    return rules


def check(module_file: Path | None, ids: list[str] | None, files: list[str]) -> Report:
    """The rules' report on the files, which lie in Bazel's execution root."""
    module = module_file_directory(module_file) if module_file else ""
    sources = {repository_path(file, module): Path(file) for file in files}
    workspace = Workspace(Path.cwd(), tuple(sources), sources)
    return run(Context(workspace, NoEvidence(), NoEvidence()), selected(ids))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-file", type=Path)
    parser.add_argument(
        "--rule", action="append", help="Run only this rule ID; repeatable"
    )
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    try:
        report = check(args.module_file, args.rule, args.files)
    except ValueError as error:
        print(f"Convention check could not complete: {error}")
        return 2
    for diagnostic in report.diagnostics:
        print(diagnostic)
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
