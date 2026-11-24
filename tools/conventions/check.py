"""Run selected convention rules against a shared repository context."""

import argparse
import os
import sys
from pathlib import Path

from tools.conventions.context import Bazel, Buildozer, Context, Workspace, run_tool
from tools.conventions.framework import run
from tools.conventions.registry import select


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("buildozer", type=Path)
    parser.add_argument(
        "--rule", action="append", help="Run only this rule ID; repeatable"
    )
    parser.add_argument("--list-rules", action="store_true")
    args = parser.parse_args()
    try:
        rules = select(args.rule)
        if args.list_rules:
            for rule in rules:
                print(f"{rule.info.id}: {rule.info.title} ({rule.info.documentation})")
            return 0
        root = Path(os.environ["BUILD_WORKSPACE_DIRECTORY"])
        files = run_tool(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"], root
        ).splitlines()
        context = Context(
            Workspace(root, tuple(files)),
            Buildozer(root, args.buildozer.resolve()),
            Bazel(root),
        )
        report = run(context, rules)
    # Evidence tools raise EvidenceError, a ValueError.
    except (ValueError, OSError) as error:
        print(f"Convention check could not complete: {error}", file=sys.stderr)
        return 2
    for diagnostic in report.not_checked:
        print(diagnostic)
    for diagnostic in report.violations:
        print(diagnostic, file=sys.stderr)
    if report.failures:
        return 1
    print("Automated convention checks passed in every owned Bazel module.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
