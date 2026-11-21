"""RG015: add-on modules share one layout, and every add-on's backends live in native/."""

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import BUILD_FILES, Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo

ADDONS = Path("addons")
# The files every module addons/<directory> owns, as tools/addons/template has them.
REQUIRED = (
    ".bazelrc",
    ".bazelversion",
    ".gitattributes",
    ".gitignore",
    "BUILD.bazel",
    "MODULE.bazel",
    "README.md",
    "REPO.bazel",
    "addon.pkl",
    "presubmit.yml",
    "examples/.bazelrc",
    "examples/.bazelversion",
    "examples/BUILD.bazel",
    "examples/MODULE.bazel",
)
# The shared settings each module's .bazelrc files import.
IMPORTS = {
    ".bazelrc": "import %workspace%/../module.bazelrc",
    "examples/.bazelrc": "import %workspace%/../../examples.bazelrc",
}
# What addon.pkl may name: the lanes hk.pkl runs and the hosts of the host lane.
ADDON_VALUES = {"lanes": {"host", "android", "ios"}, "hosts": {"linux", "macos"}}
# The targets the generic lanes build in each example project (tools/addons/lanes.py).
PROJECT_TARGETS = ("app", "edit", "pack")
LIST = re.compile(r"^(\w+)\s*=\s*List\(([^)]*)\)\s*$")
NAME = re.compile(r'\bname\s*=\s*"([^"]+)"')
EXTENSION = re.compile(r'godot_cc_extension\(\s*name\s*=\s*"([^"]+)"')


def at(path: Path | str) -> Location:
    return Location(Path(path).as_posix(), 1)


def addon_values(text: str) -> dict[str, list[str]]:
    """The `name = List(...)` properties of an addon.pkl, without its comments."""
    values = {}
    for line in text.splitlines():
        if (match := LIST.match(line.split("//")[0].strip())) is not None:
            values[match[1]] = re.findall(r'"([^"]*)"', match[2])
    return values


class AddonModuleLayout:
    info = RuleInfo(
        "RG015",
        "Add-on modules share one layout",
        "docs/public/conventions.md#rg015",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        yield from self.backends(workspace)
        modules = sorted(
            Path(name).parent
            for name in workspace.files
            if Path(name).name == "MODULE.bazel" and Path(name).parent.parent == ADDONS
        )
        for module in modules:
            yield from self.module(workspace, module)
        yield from self.extensions(workspace, modules)

    @staticmethod
    def backends(workspace: Workspace) -> Iterable[Finding]:
        """One finding per backends/ directory that is not an add-on's native/backends/."""
        misplaced: dict[Path, str] = {}
        for name in workspace.files:
            parts = Path(name).parts
            for index, part in enumerate(parts[:-1]):
                if part == "backends" and (index == 0 or parts[index - 1] != "native"):
                    misplaced.setdefault(Path(*parts[: index + 1]), name)
        for directory, name in sorted(misplaced.items()):
            yield Finding(
                at(name),
                f"an add-on's backends belong in its native/backends/: {directory.as_posix()}",
            )

    def module(self, workspace: Workspace, module: Path) -> Iterable[Finding]:
        manifest = module / "MODULE.bazel"
        for relative in REQUIRED:
            if (module / relative).as_posix() not in workspace.file_set:
                yield Finding(at(manifest), f"add-on module must own {module / relative}")
        expected = f"autoload_{module.name}"
        declared = NAME.search(workspace.text(manifest.as_posix()))
        if declared is None or declared[1] != expected:
            yield Finding(at(manifest), f"add-on module must be named {expected}")
        for relative, line in IMPORTS.items():
            path = (module / relative).as_posix()
            if (
                path in workspace.file_set
                and line not in workspace.text(path).splitlines()
            ):
                yield Finding(at(path), f"must import the shared settings: {line}")
        yield from self.addon_pkl(workspace, module / "addon.pkl")
        yield from self.projects(workspace, module / "examples/projects")

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
            for target in PROJECT_TARGETS:
                if target not in names:
                    yield Finding(at(build), f"example project must define :{target}")

    @staticmethod
    def extensions(workspace: Workspace, modules: list[Path]) -> Iterable[Finding]:
        """Extension names are unique across modules: on iOS they name the frameworks."""
        owners: dict[str, list[str]] = defaultdict(list)
        for name in workspace.files:
            path = Path(name)
            if path.name in BUILD_FILES and any(path.is_relative_to(m) for m in modules):
                for extension in EXTENSION.findall(workspace.text(name)):
                    owners[extension].append(name)
        for extension, builds in sorted(owners.items()):
            for build in builds[1:]:
                yield Finding(
                    at(build), f"extension name {extension} is taken by {builds[0]}"
                )
