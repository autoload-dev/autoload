"""
addon-module-examples-define-edit-and-pack: every add-on module has an example project in
examples/addons/<module>/, and each of its example projects defines edit and pack.
"""

from collections.abc import Iterable
from pathlib import Path

from tools.addons.modules import example_projects, examples_path
from tools.conventions.addon_modules import addon_module_paths, at
from tools.conventions.context import BUILD_FILES, Context, Workspace
from tools.conventions.framework import Finding, RuleInfo

# The targets each example project defines.
PROJECT_TARGETS = ("edit", "pack")


def example_builds(workspace: Workspace, module: Path) -> list[Path]:
    """
    The BUILD files of the module's example projects in the root module:
    examples/addons/<module>/ itself, or each of its subdirectories with a project.
    """
    projects = example_projects(examples_path(module.name), workspace.configured)
    return sorted(
        project / build
        for project in projects
        for build in BUILD_FILES
        if (project / build).as_posix() in workspace.file_set
    )


def project_findings(build: Path, declared: frozenset[str | None]) -> Iterable[Finding]:
    """The targets an example project's BUILD file lacks, or that it cannot tell."""
    missing = sorted(set(PROJECT_TARGETS) - declared)
    if missing and None in declared:
        yield Finding(
            at(build),
            f"cannot read every target name of {build.parent.as_posix()}",
            "not_checked",
        )
        return
    for target in missing:
        yield Finding(at(build), f"example project must define :{target}")


class AddonModuleExamplesDefineEditAndPack:
    info = RuleInfo(
        "addon-module-examples-define-edit-and-pack",
        "Every add-on module has example projects, each defining edit and pack",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        names = context.target_names
        for module in addon_module_paths(workspace):
            builds = example_builds(workspace, module)
            if not builds:
                yield Finding(
                    at(module / "MODULE.bazel"),
                    f"needs an example project in {examples_path(module.name)}",
                )
            for build in builds:
                yield from project_findings(
                    build, names.get(build.as_posix(), frozenset())
                )
