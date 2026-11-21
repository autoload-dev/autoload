"""RG015: add-on modules share one layout, and every add-on's backends live in native/."""

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tools.addons.modules import HOSTS, LANES, addon_values, module_attributes
from tools.addons.new import template_files
from tools.conventions.context import BUILD_FILES, Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo

ADDONS = Path("addons")
# The files every module addons/<directory> owns: those of the generator's template, but
# its example project, which a module may name and shape as it likes.
REQUIRED = tuple(
    relative
    for _, relative in template_files("module")
    if not relative.startswith("examples/projects/")
)
# The shared settings each module's .bazelrc files import.
IMPORTS = {
    ".bazelrc": "import %workspace%/../module.bazelrc",
    "examples/.bazelrc": "import %workspace%/../../examples.bazelrc",
}
# What addon.pkl may name.
ADDON_VALUES = {"lanes": set(LANES), "hosts": set(HOSTS)}
# The targets the generic lanes build in each example project (tools/addons/lanes.py).
PROJECT_TARGETS = ("app", "edit", "pack")
NAME = re.compile(r'\bname\s*=\s*"([^"]+)"')
EXTENSION = re.compile(r'godot_cc_extension\(\s*name\s*=\s*"([^"]+)"')


def at(path: Path | str) -> Location:
    return Location(Path(path).as_posix(), 1)


def backends_directory(name: str) -> Path | None:
    """The first backends/ directory of a path that is not an add-on's native/backends/."""
    parts = Path(name).parts
    for index, part in enumerate(parts[:-1]):
        previous = parts[index - 1] if index else ""
        if part == "backends" and previous != "native":
            return Path(*parts[: index + 1])
    return None


def in_modules(name: str, modules: list[Path]) -> bool:
    return any(Path(name).is_relative_to(module) for module in modules)


def extension_owners(workspace: Workspace, modules: list[Path]) -> dict[str, list[str]]:
    """The BUILD files of the modules that declare each extension name, in file order."""
    owners: dict[str, list[str]] = defaultdict(list)
    builds = [
        name
        for name in workspace.files
        if Path(name).name in BUILD_FILES and in_modules(name, modules)
    ]
    for build in builds:
        for extension in EXTENSION.findall(workspace.text(build)):
            owners[extension].append(build)
    return owners


class AddonModuleLayout:
    info = RuleInfo(
        "RG015",
        "Add-on modules share one layout",
        "docs/public/conventions.md#rg015",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        yield from self.backends(workspace)
        modules = sorted(path for path in workspace.module_paths if path.parent == ADDONS)
        for module in modules:
            yield from self.files(workspace, module)
            yield from self.imports(workspace, module)
            yield from self.addon_pkl(workspace, module / "addon.pkl")
            yield from self.projects(workspace, module / "examples/projects")
        yield from self.extensions(workspace, modules)

    @staticmethod
    def backends(workspace: Workspace) -> Iterable[Finding]:
        """One finding per backends/ directory that is not an add-on's native/backends/."""
        misplaced: dict[Path, str] = {}
        for name in workspace.files:
            if (directory := backends_directory(name)) is not None:
                misplaced.setdefault(directory, name)
        for directory, name in sorted(misplaced.items()):
            yield Finding(
                at(name),
                f"an add-on's backends belong in its native/backends/: {directory.as_posix()}",
            )

    @staticmethod
    def files(workspace: Workspace, module: Path) -> Iterable[Finding]:
        manifest = module / "MODULE.bazel"
        for relative in REQUIRED:
            if (module / relative).as_posix() not in workspace.file_set:
                yield Finding(at(manifest), f"add-on module must own {module / relative}")
        expected = f"autoload_{module.name}"
        if module_attributes(workspace.text(manifest.as_posix())).get("name") != expected:
            yield Finding(at(manifest), f"add-on module must be named {expected}")

    @staticmethod
    def imports(workspace: Workspace, module: Path) -> Iterable[Finding]:
        present = [
            (path, line)
            for relative, line in IMPORTS.items()
            if (path := (module / relative).as_posix()) in workspace.file_set
        ]
        for path, line in present:
            if line not in workspace.text(path).splitlines():
                yield Finding(at(path), f"must import the shared settings: {line}")

    @staticmethod
    def addon_pkl(workspace: Workspace, path: Path) -> Iterable[Finding]:
        if path.as_posix() not in workspace.file_set:
            return
        values = addon_values(workspace.text(path.as_posix()))
        if values.keys() != ADDON_VALUES.keys():
            yield Finding(at(path), "addon.pkl sets exactly lanes and hosts, each a List")
            return
        for key, allowed in ADDON_VALUES.items():
            if not values[key] or not set(values[key]) <= allowed:
                yield Finding(
                    at(path),
                    f"addon.pkl's {key} names some of {', '.join(sorted(allowed))}",
                )

    @staticmethod
    def projects(workspace: Workspace, root: Path) -> Iterable[Finding]:
        builds = sorted(
            Path(name)
            for name in workspace.files
            if Path(name).parent.parent == root and Path(name).name in BUILD_FILES
        )
        if not builds:
            yield Finding(
                at(root.parent / "MODULE.bazel"), f"needs an example project in {root}"
            )
        for build in builds:
            names = set(NAME.findall(workspace.text(build.as_posix())))
            for target in sorted(set(PROJECT_TARGETS) - names):
                yield Finding(at(build), f"example project must define :{target}")

    @staticmethod
    def extensions(workspace: Workspace, modules: list[Path]) -> Iterable[Finding]:
        """Extension names are unique across modules: on iOS they name the frameworks."""
        for extension, owning in sorted(extension_owners(workspace, modules).items()):
            for build in owning[1:]:
                yield Finding(
                    at(build), f"extension name {extension} is taken by {owning[0]}"
                )
