"""RG015: add-on modules share one layout, and every add-on's backends live in native/."""

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tools.addons import registry as templates
from tools.addons.modules import (
    AMENDS,
    HOSTS,
    LANES,
    PROPERTIES,
    addon_manifest,
    addon_values,
    builds_apps,
    module_attributes,
    module_name,
)
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
# The registry templates each module owns in .bcr/addons/<directory>/, which the generator
# writes once with the module; publish-to-bcr reads them there.
REGISTRY = (*(relative for _, relative in template_files("bcr")), templates.METADATA)
# The shared settings each module's .bazelrc files import.
IMPORTS = {
    ".bazelrc": "import %workspace%/../module.bazelrc",
    "examples/.bazelrc": "import %workspace%/../../examples.bazelrc",
}
# The values addon.pkl may name, by property; hk's Pkl evaluator does not check the schema's
# types.
ADDON_VALUES = {"lanes": set(LANES), "hosts": set(HOSTS)}
# What only a module with an application lane owns: its examples' Maven graph and their
# provisioning profile.
APP_FILES = ("examples/BUILD.bazel", "examples/maven_install.json")
# The targets the generic lanes build in each example project (tools/addons/lanes.py); the
# application lanes build :app too.
PROJECT_TARGETS = ("edit", "pack")
APP_TARGET = "app"
NAME = re.compile(r'\bname\s*=\s*"([^"]+)"')
EXTENSION = re.compile(r'godot_cc_extension\(\s*name\s*=\s*"([^"]+)"')
# A property an addon.pkl sets, whatever its value: the tools read only one-line Lists.
ASSIGNMENT = re.compile(r"^(\w+)\s*(?::[^=]*)?=")


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


def unlisted_values(listed: list[str], allowed: set[str]) -> bool:
    """Whether a List names nothing, something it may not name, or a value twice."""
    return not listed or not set(listed) <= allowed or len(set(listed)) != len(listed)


def property_problems(assigned: set[str], values: dict[str, list[str]]) -> Iterable[str]:
    """Properties an addon.pkl may not set, sets in a form tools cannot read, or leaves out."""
    if unknown := sorted(assigned - set(PROPERTIES)):
        yield f"addon.pkl sets no {', '.join(unknown)}"
    for key in sorted((assigned & set(PROPERTIES)) - set(values)):
        yield f"addon.pkl's {key} is a List(...) on one line"
    if "lanes" not in assigned:
        yield "addon.pkl sets lanes"


def value_problems(values: dict[str, list[str]]) -> Iterable[str]:
    """Lists of an addon.pkl that name something the schema does not allow."""
    for key, allowed in ADDON_VALUES.items():
        if key in values and unlisted_values(values[key], allowed):
            yield f"addon.pkl's {key} names some of {', '.join(sorted(allowed))}, once each"


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
            builds_apps = self.builds_apps(workspace, module / "addon.pkl")
            yield from self.files(workspace, module, builds_apps)
            yield from self.registry(workspace, module)
            yield from self.imports(workspace, module)
            yield from self.addon_pkl(workspace, module / "addon.pkl")
            yield from self.projects(workspace, module / "examples/projects", builds_apps)
        yield from self.extensions(workspace, modules)
        yield from self.orphaned_templates(workspace, modules)

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
    def builds_apps(workspace: Workspace, path: Path) -> bool:
        """Whether a module's addon.pkl names an application lane, or there is none yet."""
        if path.as_posix() not in workspace.file_set:
            return True
        return builds_apps(
            addon_manifest(workspace.text(path.as_posix())).get("lanes", LANES)
        )

    @staticmethod
    def files(workspace: Workspace, module: Path, builds_apps: bool) -> Iterable[Finding]:
        manifest = module / "MODULE.bazel"
        required = [
            relative for relative in REQUIRED if builds_apps or relative not in APP_FILES
        ]
        for relative in required:
            if (module / relative).as_posix() not in workspace.file_set:
                yield Finding(at(manifest), f"add-on module must own {module / relative}")
        expected = module_name(module.name)
        if module_attributes(workspace.text(manifest.as_posix())).get("name") != expected:
            yield Finding(at(manifest), f"add-on module must be named {expected}")

    @staticmethod
    def registry(workspace: Workspace, module: Path) -> Iterable[Finding]:
        """The module's registry templates exist and describe the module's own releases."""
        directory = templates.templates_directory(module.name)
        for name in REGISTRY:
            path = (directory / name).as_posix()
            if path not in workspace.file_set:
                yield Finding(
                    at(module / "MODULE.bazel"), f"add-on module must own {path}"
                )
            elif message := templates.problem(
                name, workspace.text(path), module.name, workspace.root
            ):
                yield Finding(at(path), message)

    @staticmethod
    def orphaned_templates(
        workspace: Workspace, modules: list[Path]
    ) -> Iterable[Finding]:
        """Registry templates of a module that no longer exists are removed with it."""
        owners = {owner for name in workspace.files if (owner := templates.owner(name))}
        for directory in sorted(owners - {module.name for module in modules}):
            path = templates.templates_directory(directory)
            yield Finding(at(path), f"no add-on module owns {path.as_posix()}")

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
        """addon.pkl amends the schema and sets only its properties, with known values."""
        if path.as_posix() not in workspace.file_set:
            return
        text = workspace.text(path.as_posix())
        lines = [line.split("//")[0].strip() for line in text.splitlines()]
        if next((line for line in lines if line), "") != AMENDS:
            yield Finding(at(path), f"addon.pkl starts with {AMENDS}")
        assigned = {match[1] for line in lines if (match := ASSIGNMENT.match(line))}
        values = addon_values(text)
        for message in [*property_problems(assigned, values), *value_problems(values)]:
            yield Finding(at(path), message)

    @staticmethod
    def projects(
        workspace: Workspace, root: Path, builds_apps: bool
    ) -> Iterable[Finding]:
        builds = sorted(
            Path(name)
            for name in workspace.files
            if Path(name).parent.parent == root and Path(name).name in BUILD_FILES
        )
        if not builds:
            yield Finding(
                at(root.parent / "MODULE.bazel"), f"needs an example project in {root}"
            )
        targets = set(PROJECT_TARGETS) | ({APP_TARGET} if builds_apps else set())
        for build in builds:
            names = set(NAME.findall(workspace.text(build.as_posix())))
            for target in sorted(targets - names):
                yield Finding(at(build), f"example project must define :{target}")

    @staticmethod
    def extensions(workspace: Workspace, modules: list[Path]) -> Iterable[Finding]:
        """Extension names are unique across modules: on iOS they name the frameworks."""
        for extension, owning in sorted(extension_owners(workspace, modules).items()):
            for build in owning[1:]:
                yield Finding(
                    at(build), f"extension name {extension} is taken by {owning[0]}"
                )
