"""
no-test-only-dependencies-in-addon-modules: an add-on module has no regular dependency
that only its tests/ packages load from, since every consumer inherits it.
"""

from collections.abc import Iterable
from pathlib import Path

from tools.conventions.addon_modules import (
    addon_module_paths,
    at,
    names_package,
    starlark_files,
)
from tools.conventions.context import Context, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.layout import TESTS
from tools.setup.modules import declarations, literals


def regular_dependencies(manifest: str) -> set[str]:
    """The repositories of a MODULE.bazel's regular bazel_deps, by the name it uses."""
    deps = (literals(d.keywords) for d in declarations(manifest) if d.kind == "bazel_dep")
    return {
        dep.get("repo_name", dep["name"])
        for dep in deps
        if "name" in dep and not dep.get("dev_dependency")
    }


def only_tests_load(workspace: Workspace, files: list[str], repository: str) -> bool:
    """Whether some of the files name a repository in a string, all of them in tests/."""
    labels = (f"@{repository}",)
    uses = [
        Path(name)
        for name in files
        if any(names_package(value, labels) for value in workspace.strings(name))
    ]
    return bool(uses) and all(TESTS in use.parts for use in uses)


def tests_only_dependencies(workspace: Workspace, module: Path) -> list[str]:
    """The regular dependencies of a module that only its tests load from."""
    regular = regular_dependencies(workspace.text((module / "MODULE.bazel").as_posix()))
    files = starlark_files(workspace, module)
    return sorted(name for name in regular if only_tests_load(workspace, files, name))


class NoTestOnlyDependenciesInAddonModules:
    info = RuleInfo(
        "no-test-only-dependencies-in-addon-modules",
        "Add-on modules have no regular dependency that only their tests load",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        for module in addon_module_paths(workspace):
            for name in tests_only_dependencies(workspace, module):
                yield Finding(
                    at(module / "MODULE.bazel"),
                    f"only tests load {name}, which every consumer inherits: "
                    f"test with it from e2e/addons/{module.name}/",
                )
