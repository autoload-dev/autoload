"""
application-content-under-main: the resource inputs an application owns live under the
main/ of its physical project.
"""

from collections.abc import Iterable, Mapping
from pathlib import Path

from tools.conventions.context import (
    Context,
    Fact,
    GeneratedFile,
    Location,
    Module,
    SourceFile,
    Target,
    Workspace,
)
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.layout import is_end_to_end

# The rule of the resources a project's operations select.
RESOURCES = "godot_resources"


def unknown_membership(target: Target) -> str | None:
    """What keeps a resources target's role or members unknown, if anything."""
    if "testonly" not in target.booleans:
        return f"cannot determine resource role for {target.label}"
    if (
        "srcs" not in target.label_lists
        or "resource_paths" not in target.label_keyed_strings
    ):
        return f"cannot determine resource membership for {target.label}"
    return None


def members(target: Target) -> list[tuple[Target, str]]:
    """A resources target with each label it selects, through srcs and resource_paths."""
    labels = [*target.label_lists["srcs"], *target.label_keyed_strings["resource_paths"]]
    return [(target, label) for label in labels]


def is_output(fact: Fact) -> bool:
    """Whether a selected label is built rather than authored."""
    return isinstance(fact, GeneratedFile) or (
        isinstance(fact, Target) and bool(fact.outputs)
    )


class Sources:
    """The authored sources the resources targets select, each test-only if all its users are."""

    def __init__(self) -> None:
        self.test_only: dict[Path, bool] = {}

    def collect(self, context: Context, module: Module) -> Iterable[Finding]:
        """Add the sources of a module's resources targets; report what stays unknown."""
        targets = [t for t in context.bazel.rules(module) if t.kind == RESOURCES]
        for target in targets:
            if message := unknown_membership(target):
                yield Finding(target.location, message, "not_checked")
        selected = [
            pair
            for target in targets
            if unknown_membership(target) is None
            for pair in members(target)
        ]
        labels = tuple(sorted({label for _, label in selected}))
        facts = context.bazel.inspect(module, labels) if labels else {}
        yield from self._record(selected, facts)

    def _record(
        self, selected: list[tuple[Target, str]], facts: Mapping[str, Fact]
    ) -> Iterable[Finding]:
        """Record the authored sources of the selected labels; report the unresolved ones."""
        unresolved: set[tuple[Location, str]] = set()
        for target, label in selected:
            fact = facts[label]
            if isinstance(fact, SourceFile):
                users = self.test_only.get(fact.path, True)
                self.test_only[fact.path] = users and target.booleans["testonly"]
            elif not is_output(fact):
                unresolved.add((target.location, label))
        for location, label in sorted(
            unresolved, key=lambda item: (item[0].line, item[1])
        ):
            yield Finding(
                location,
                f"cannot determine authored files supplied by {label}",
                "not_checked",
            )


class ApplicationContentUnderMain:
    info = RuleInfo(
        "application-content-under-main",
        "Application content lives under its project's main/",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        configurations = {path.parent for path in workspace.godot_configurations}
        sources = Sources()
        for module in workspace.loaded_modules:
            yield from sources.collect(context, module)
        for absolute, test_only in sorted(sources.test_only.items()):
            main = self._misplaced(workspace, absolute, test_only, configurations)
            if main is not None:
                path = absolute.relative_to(workspace.root)
                yield Finding(
                    Location(path.as_posix(), 1),
                    f"application content must live under {main}/",
                )

    def _misplaced(
        self,
        workspace: Workspace,
        absolute: Path,
        test_only: bool,
        configurations: set[Path],
    ) -> Path | None:
        """
        The main/ a source of the workspace belongs under but lies outside of, if any: none
        for a project's configuration, and none for a test-only input where tests may lie.
        """
        if not absolute.is_relative_to(workspace.root):
            return None
        path = absolute.relative_to(workspace.root)
        owner = self._owner(workspace, path, configurations)
        if owner is None or path.name == "project.godot":
            return None
        if test_only and self._test_input(path, owner):
            return None
        return None if path.is_relative_to(owner / "main") else owner / "main"

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
