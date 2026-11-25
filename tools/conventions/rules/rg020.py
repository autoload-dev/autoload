"""RG020: every released module has a flat registry test module in its bcr/ directory."""

from collections.abc import Iterable
from pathlib import Path

from tools.addons.modules import example_projects
from tools.addons.registry import presubmit, registry_test_module
from tools.conventions.context import Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.rules.rg023 import released
from tools.setup.modules import BCR


class RegistryTestModules:
    info = RuleInfo(
        "RG020",
        "Released modules have a flat registry test module in bcr/",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        for module in released(workspace):
            yield from self.ignored(workspace, module)
            test_module = yield from self.named(workspace, module)
            if test_module is not None:
                yield from self.flat(workspace, test_module)

    @staticmethod
    def ignored(workspace: Workspace, module: Path) -> Iterable[Finding]:
        path = (module / ".bazelignore").as_posix()
        text = workspace.text(path) if path in workspace.file_set else ""
        if BCR not in (line.strip() for line in text.splitlines()):
            yield Finding(
                Location(path, 1), f"must list {BCR}, the registry test modules"
            )

    @staticmethod
    def named(workspace: Workspace, module: Path) -> Iterable[Finding]:
        """Report a presubmit that names no test module in bcr/; return the test module."""
        path = presubmit(module).as_posix()
        text = workspace.text(path) if path in workspace.file_set else ""
        found = registry_test_module(text)
        if found is None:
            yield Finding(Location(path, 1), "must run a bcr_test_module of the module")
            return None
        named = Path(found)
        if named.parent != Path(BCR):
            yield Finding(
                Location(path, 1),
                f"{module}/{named}: registry test modules live in {module}/{BCR}/<name>/",
            )
            return None
        test_module = module / named
        if (test_module / "MODULE.bazel").as_posix() not in workspace.file_set:
            yield Finding(Location(path, 1), f"{test_module}: no such module")
            return None
        return test_module

    @staticmethod
    def flat(workspace: Workspace, test_module: Path) -> Iterable[Finding]:
        """A test module is a consumer: one project at its root, or one per subdirectory."""
        configured = [d for d in workspace.configured if d.is_relative_to(test_module)]
        projects = set(example_projects(test_module, configured))
        for directory in sorted(set(configured) - projects):
            yield Finding(
                Location((directory / "project.godot").as_posix(), 1),
                f"a project of a registry test module lies at {test_module} or directly "
                "in a directory of it",
            )
