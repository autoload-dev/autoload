"""
Evidence the add-on module rules share: the add-on modules, the parsed calls and target
names of the BUILD files, and the Starlark files of a module and the labels in them.
"""

from pathlib import Path

from tools.addons.new import LICENSE, template_files
from tools.conventions.context import BUILD_FILES, Location, Workspace
from tools.setup.modules import is_addon_module

# The files every module addons/<directory> has: those of the generator's module template and
# its copy of the repository's license.
MODULE_FILES = (*(relative for _, relative in template_files("module")), LICENSE)


def at(path: Path | str) -> Location:
    """The first line of a file, where a finding about the whole file stands."""
    return Location(Path(path).as_posix(), 1)


def addon_module_paths(workspace: Workspace) -> list[Path]:
    """Every add-on module addons/<module>/ of the workspace, in order."""
    return sorted(filter(is_addon_module, workspace.module_paths))


def is_starlark(name: str) -> bool:
    """Whether a file is a BUILD file, a MODULE.bazel or a .bzl file."""
    path = Path(name)
    return (
        path.name in BUILD_FILES or path.name == "MODULE.bazel" or path.suffix == ".bzl"
    )


def names_package(value: str, labels: tuple[str, ...]) -> bool:
    """Whether a string is one of the labels or a label below them."""
    return any(
        value == label or value.startswith((f"{label}:", f"{label}/")) for label in labels
    )


def module_files(workspace: Workspace, module: Path) -> list[str]:
    """The files of a module, without those of its nested modules."""
    prefix = f"{module.as_posix()}/"
    # The prefix test spares the owner lookup for files of other modules.
    return [
        name
        for name in workspace.files
        if name.startswith(prefix) and workspace.owner(name) == module
    ]


def starlark_files(workspace: Workspace, module: Path) -> list[str]:
    """
    The Starlark files of a module: its MODULE.bazel, BUILD and .bzl files and the build
    files of its third-party archives, without those of its nested modules.
    """
    return [name for name in module_files(workspace, module) if is_starlark(name)]
