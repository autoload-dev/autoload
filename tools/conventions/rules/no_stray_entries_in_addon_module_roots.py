"""
no-stray-entries-in-addon-module-roots: an add-on module's root holds only its template
files and lock file, its add-ons, third_party/, tests/, bcr/ and packages that a Starlark
file outside them names by label.
"""

from collections.abc import Iterable, Mapping
from pathlib import Path

from tools.addons.modules import module_name
from tools.conventions.addon_modules import (
    MODULE_FILES,
    addon_module_paths,
    at,
    is_starlark,
    module_files,
    names_package,
)
from tools.conventions.context import BUILD_FILES, Context, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.setup.modules import BCR

# What a module's root holds besides its add-ons and the packages that other packages load
# by label: the template's files, its lock file and the directories every module may have.
ROOT_FILES = frozenset(
    {*(relative for relative in MODULE_FILES if "/" not in relative), "MODULE.bazel.lock"}
)
ROOT_DIRECTORIES = frozenset({"third_party", "tests", BCR})
ROOT_ENTRIES = ", ".join(
    ["its files", "its add-ons", *(f"{name}/" for name in sorted(ROOT_DIRECTORIES))]
)


def module_root_entries(workspace: Workspace, module: Path) -> dict[str, bool]:
    """The entries of a module's root, by name, and whether each is a file."""
    entries = {}
    for name in module_files(workspace, module):
        parts = Path(name).relative_to(module).parts
        entries[parts[0]] = len(parts) == 1
    return entries


def referenced_by_label(workspace: Workspace, module: Path, package: Path) -> bool:
    """
    Whether a Starlark file outside a package of the module's root names it by label: one of
    the module's other packages as `//<package>`, any other module as `@<module>//<package>`.
    """
    local = f"//{package.name}"
    remote = f"@{module_name(module.name)}{local}"
    for name in workspace.files:
        if not is_starlark(name) or Path(name).is_relative_to(package):
            continue
        labels = (local, remote) if workspace.owner(name) == module else (remote,)
        if any(names_package(value, labels) for value in workspace.strings(name)):
            return True
    return False


def allowed_entry(
    workspace: Workspace,
    module: Path,
    entry: tuple[str, bool],
    names: Mapping[str, frozenset[str | None]],
) -> bool:
    """
    Whether a root entry, by name and whether it is a file, is a module file, a directory
    every module may have, an add-on, whose BUILD file declares a target named like its
    directory, or a package that other packages load by label.
    """
    name, is_file = entry
    if is_file:
        return name in ROOT_FILES
    path = module / name
    builds = ((path / build).as_posix() for build in BUILD_FILES)
    if name in ROOT_DIRECTORIES:
        return True
    package = [build for build in builds if build in workspace.file_set]
    return any(name in names.get(build, ()) for build in package) or (
        bool(package) and referenced_by_label(workspace, module, path)
    )


class NoStrayEntriesInAddonModuleRoots:
    info = RuleInfo(
        "no-stray-entries-in-addon-module-roots",
        "An add-on module's root holds only its files, add-ons and the packages others load",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        names = context.target_names
        for module in addon_module_paths(workspace):
            for entry in sorted(module_root_entries(workspace, module).items()):
                if not allowed_entry(workspace, module, entry, names):
                    path = module / entry[0]
                    yield Finding(
                        at(path),
                        f"{path}: the module's root holds only {ROOT_ENTRIES} and "
                        "packages that other packages load by label",
                    )
