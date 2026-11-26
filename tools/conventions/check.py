"""Run selected convention rules against a shared repository context."""

import argparse
import os
import sys
from pathlib import Path

from tools.conventions.bazel import Bazel, Scope
from tools.conventions.context import Buildozer, Context, Workspace, run_tool
from tools.conventions.cache import (
    ReportCache,
    cache_directory,
    checker_sources,
    evidence_key,
)
from tools.conventions.framework import Diagnostic, Rule, report, run
from tools.conventions.registry import select
from tools.setup.modules import is_addon_module


def development_bazel(workspace: Workspace, buildozer: Buildozer) -> Bazel:
    """
    Load the modules in two workspaces: the ruleset in its own, whose development dependencies
    only it sees, and the add-on modules in the root module's, which depends on each of them
    under its module name.
    """
    root = workspace.root
    return Bazel(
        root,
        {
            module: Scope(root, buildozer.module_name(module))
            if is_addon_module(module.path)
            else Scope(root / module.path)
            for module in workspace.loaded_modules
        },
    )


def evaluated_diagnostics(
    context: Context, rules: tuple[Rule, ...]
) -> tuple[Diagnostic, ...]:
    """
    The diagnostics of the rules that read Bazel's loading evidence, from the result cache
    when nothing they depend on changed; only a miss loads Bazel.
    """
    evaluated = tuple(rule for rule in rules if rule.info.evaluated)
    if not evaluated:
        return ()
    cache = ReportCache(cache_directory())
    key = evidence_key(context.workspace, evaluated, checker_sources())
    cached = cache.load(key, evaluated)
    if cached is not None:
        print("Reused the cached findings of the rules that read Bazel's evidence.")
        return cached
    diagnostics = run(context, evaluated).diagnostics
    cache.store(key, diagnostics)
    return diagnostics


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
        workspace = Workspace(root, tuple(files))
        buildozer = Buildozer(root, args.buildozer.resolve())
        context = Context(workspace, buildozer, development_bazel(workspace, buildozer))
        result = report(
            (
                *evaluated_diagnostics(context, rules),
                *run(context, (r for r in rules if not r.info.evaluated)).diagnostics,
            )
        )
    # Evidence tools raise EvidenceError, a ValueError.
    except (ValueError, OSError) as error:
        print(f"Convention check could not complete: {error}", file=sys.stderr)
        return 2
    for diagnostic in result.not_checked:
        print(diagnostic)
    for diagnostic in result.violations:
        print(diagnostic, file=sys.stderr)
    if result.failures:
        return 1
    print("Automated convention checks passed in every owned Bazel module.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
