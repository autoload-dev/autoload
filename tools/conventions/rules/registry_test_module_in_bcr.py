"""
registry-test-module-in-bcr: every released module has a registry test module in its bcr/
directory.
"""

from collections.abc import Iterable
from pathlib import Path

from tools.addons.registry import presubmit, registry_test_module
from tools.conventions.context import Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.setup.modules import BCR, bazelignore_entries, released_modules


class RegistryTestModules:
    info = RuleInfo(
        "registry-test-module-in-bcr",
        "Released modules have a registry test module in bcr/",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        for module in released_modules(workspace.module_paths):
            yield from self.ignored(workspace, module)
            yield from self.named(workspace, module)

    @staticmethod
    def ignored(workspace: Workspace, module: Path) -> Iterable[Finding]:
        path = (module / ".bazelignore").as_posix()
        if BCR not in bazelignore_entries(
            workspace.text(path) if path in workspace.file_set else ""
        ):
            yield Finding(
                Location(path, 1), f"must list {BCR}, the registry test modules"
            )

    @staticmethod
    def named(workspace: Workspace, module: Path) -> Iterable[Finding]:
        """Report a presubmit that names no existing test module in bcr/."""
        path = presubmit(module).as_posix()
        found = registry_test_module(
            workspace.text(path) if path in workspace.file_set else ""
        )
        if found is None:
            yield Finding(Location(path, 1), "must run a bcr_test_module of the module")
            return
        named = Path(found)
        if named.parent != Path(BCR):
            yield Finding(
                Location(path, 1),
                f"{module}/{named}: registry test modules live in {module}/{BCR}/<name>/",
            )
            return
        test_module = module / named
        if (test_module / "MODULE.bazel").as_posix() not in workspace.file_set:
            yield Finding(Location(path, 1), f"{test_module}: no such module")
