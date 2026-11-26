"""Run selected convention rules against a shared repository context."""

import argparse
import os
import sys
from pathlib import Path

from tools.addons.modules import module_name
from tools.conventions.bazel import Bazel, Scope
from tools.conventions.cache import QueryCache, cache_directory, loading_inputs
from tools.conventions.context import Buildozer, Context, Workspace, run_tool
from tools.conventions.framework import run
from tools.conventions.registry import select
from tools.setup.modules import is_addon_module


def development_bazel(workspace: Workspace) -> Bazel:
    """
    Load the modules in two workspaces: the ruleset in its own, whose development dependencies
    only it sees, and the add-on modules in the root module's, which depends on each of them
    under its module name (RG015). The queries' output is cached while nothing that loading
    reads changes.
    """
    root = workspace.root
    return Bazel(
        root,
        {
            module: Scope(root, module_name(module.path.name))
            if is_addon_module(module.path)
            else Scope(root / module.path)
            for module in workspace.loaded_modules
        },
        QueryCache(cache_directory(), lambda: loading_inputs(workspace)),
    )


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
        context = Context(workspace, buildozer, development_bazel(workspace))
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
