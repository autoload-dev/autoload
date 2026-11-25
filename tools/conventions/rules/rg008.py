"""
RG008: application-owned resource inputs live under their physical project's main/, and its
tests in its tests/ package.
"""

from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import (
    BUILD_FILES,
    Context,
    GeneratedFile,
    Location,
    SourceFile,
    Target,
    Workspace,
)
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.layout import EXAMPLES_ROOT, is_end_to_end
from tools.conventions.rules.rg007 import declared_operations


def is_test(kind: str, operations: frozenset[str]) -> bool:
    """Whether a call declares a test: a test operation or a rule named like one."""
    return kind in operations or kind.endswith("_test")


def root_tests(context: Context) -> Iterable[Finding]:
    """Report the tests an application project's root package declares."""
    workspace = context.workspace
    kinds = declared_operations(workspace)
    roots = {
        (project / build).as_posix(): project
        for project in workspace.projects
        if project.is_relative_to(EXAMPLES_ROOT)
        for build in BUILD_FILES
    }
    calls = {
        call for module in workspace.modules for call in context.starlark.calls(module)
    }
    for call in sorted(calls, key=lambda call: (call.location.path, call.location.line)):
        project = roots.get(call.location.path)
        if project is not None and is_test(call.kind, kinds):
            yield Finding(
                call.location,
                f"an application's tests live in {project / 'tests'}/: :{call.literal_name}",
            )


class ApplicationContent:
    info = RuleInfo(
        "RG008",
        "Application content lives under main, its tests under tests",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        yield from root_tests(context)
        workspace = context.workspace
        configurations = {path.parent for path in workspace.godot_configurations}
        sources: dict[Path, bool] = {}
        for module in workspace.modules:
            resources = [
                target
                for target in context.bazel.rules(module)
                if target.kind == "godot_resources"
            ]
            members: list[tuple[Target, str]] = []
            for target in resources:
                if "testonly" not in target.booleans:
                    yield Finding(
                        target.location,
                        f"cannot determine resource role for {target.label}",
                        "not_checked",
                    )
                    continue
                if (
                    "srcs" not in target.label_lists
                    or "resource_paths" not in target.label_keyed_strings
                ):
                    yield Finding(
                        target.location,
                        f"cannot determine resource membership for {target.label}",
                        "not_checked",
                    )
                    continue
                members.extend((target, label) for label in target.label_lists["srcs"])
                members.extend(
                    (target, label)
                    for label in target.label_keyed_strings["resource_paths"]
                )
            labels = tuple(sorted({label for _, label in members}))
            facts = context.bazel.inspect(module, labels) if labels else {}
            seen: set[tuple[Location, str]] = set()
            for target, label in members:
                fact = facts[label]
                if isinstance(fact, GeneratedFile) or (
                    isinstance(fact, Target) and fact.outputs
                ):
                    continue
                if isinstance(fact, SourceFile):
                    sources[fact.path] = (
                        sources.get(fact.path, True) and target.booleans["testonly"]
                    )
                elif (target.location, label) not in seen:
                    seen.add((target.location, label))
                    yield Finding(
                        target.location,
                        f"cannot determine authored files supplied by {label}",
                        "not_checked",
                    )
        for absolute, test_only in sorted(sources.items()):
            if not absolute.is_relative_to(workspace.root):
                continue
            path = absolute.relative_to(workspace.root)
            if path.name == "project.godot":
                continue
            owner = self._owner(workspace, path, configurations)
            if owner is not None and test_only and self._test_input(path, owner):
                continue
            if owner is not None and not path.is_relative_to(owner / "main"):
                yield Finding(
                    Location(path.as_posix(), 1),
                    f"application content must live under {owner / 'main'}/",
                )

    @staticmethod
    def _test_input(path: Path, owner: Path) -> bool:
        """
        Whether a test-only input lies where tests may: in its project's tests/, or
        anywhere in an end-to-end test project, whose suites have no prescribed place.
        """
        parts = path.relative_to(owner).parts
        return is_end_to_end(owner) or (len(parts) > 1 and parts[0] == "tests")

    @staticmethod
    def _owner(
        workspace: Workspace, path: Path, configurations: set[Path]
    ) -> Path | None:
        root = workspace.project(path)
        if root is None:
            return None
        candidates = [
            config
            for config in configurations
            if config.is_relative_to(root) and path.is_relative_to(config)
        ]
        return max(candidates, key=lambda config: len(config.parts), default=root)
