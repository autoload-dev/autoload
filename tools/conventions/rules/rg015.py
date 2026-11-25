"""RG015: add-on modules share one layout, and every add-on's backends live in native/."""

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tools.addons import registry as templates
from tools.addons.modules import (
    AMENDS,
    DESKTOPS,
    LANES,
    PROPERTIES,
    addon_manifest,
    addon_values,
    builds_apps,
    example_projects,
    examples_path,
    module_attributes,
    module_name,
)
from tools.addons.new import template_files
from tools.conventions.context import BUILD_FILES, Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.setup.modules import ADDONS as ADDON_DIRECTORY
from tools.setup.modules import BCR, is_addon_module

ADDONS = Path(ADDON_DIRECTORY)
# The files every module addons/<directory> owns: those of the generator's module template.
REQUIRED = tuple(relative for _, relative in template_files("module"))
# The registry templates each module owns in .bcr/addons/<directory>/, which the generator
# writes once with the module; publish-to-bcr reads them there.
REGISTRY = (*(relative for _, relative in template_files("bcr")), templates.METADATA)
# What a module's root holds besides its add-ons and the sharedPackages of its addon.pkl:
# the template's files, its lock file and the directories every module may have.
ROOT_FILES = frozenset(
    {*(relative for relative in REQUIRED if "/" not in relative), "MODULE.bazel.lock"}
)
ROOT_DIRECTORIES = frozenset({"third_party", "tests", BCR})
ROOT_ENTRIES = ", ".join(
    ["its files", "its add-ons", *(f"{name}/" for name in sorted(ROOT_DIRECTORIES))]
)
# The shared settings each module's .bazelrc imports.
IMPORT = "import %workspace%/../module.bazelrc"
# The values addon.pkl may name, by property: the tools read addon.pkl without evaluating
# Pkl, so nothing else checks the schema's types.
ADDON_VALUES = {"lanes": set(LANES), "desktops": set(DESKTOPS)}
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


def module_root_entries(workspace: Workspace, module: Path) -> dict[str, bool]:
    """The entries of a module's root, by name, and whether each is a file."""
    entries = {}
    prefix = f"{module.as_posix()}/"
    for name in workspace.files:
        # The prefix test spares the owner lookup for files of other modules.
        if name.startswith(prefix) and workspace.owner(name) == module:
            parts = Path(name).relative_to(module).parts
            entries[parts[0]] = len(parts) == 1
    return entries


def declared_names(context: Context) -> dict[str, set[str | None]]:
    """The names of the targets that each BUILD file declares, from its parsed calls."""
    names: dict[str, set[str | None]] = defaultdict(set)
    for module in context.workspace.modules:
        for call in context.starlark.calls(module):
            names[call.location.path].add(call.literal_name)
    return names


def allowed_entry(
    path: Path, is_file: bool, allowed: frozenset[str], names: dict[str, set[str | None]]
) -> bool:
    """
    Whether a root entry is a module file, an allowed directory or an add-on, whose BUILD
    file declares a target named like its directory.
    """
    if is_file:
        return path.name in ROOT_FILES
    builds = ((path / build).as_posix() for build in BUILD_FILES)
    return path.name in allowed or any(path.name in names[build] for build in builds)


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
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        yield from self.backends(workspace)
        modules = sorted(filter(is_addon_module, workspace.module_paths))
        names = declared_names(context)
        for module in modules:
            builds_apps = self.builds_apps(workspace, module / "addon.pkl")
            yield from self.files(workspace, module)
            yield from self.root_entries(workspace, module, names)
            yield from self.registry(workspace, module)
            yield from self.imports(workspace, module)
            yield from self.addon_pkl(workspace, module / "addon.pkl")
            yield from self.projects(workspace, module, builds_apps)
        yield from self.extensions(workspace, modules)
        yield from self.orphaned_templates(workspace, modules)

    @staticmethod
    def root_entries(
        workspace: Workspace, module: Path, names: dict[str, set[str | None]]
    ) -> Iterable[Finding]:
        """
        The entries of the module's root that are none of its files, add-ons, shared
        packages or the directories every module may have.
        """
        pkl = (module / "addon.pkl").as_posix()
        manifest = addon_manifest(
            workspace.text(pkl) if pkl in workspace.file_set else ""
        )
        allowed = ROOT_DIRECTORIES | frozenset(manifest["sharedPackages"])
        for entry, is_file in sorted(module_root_entries(workspace, module).items()):
            if not allowed_entry(module / entry, is_file, allowed, names):
                yield Finding(
                    at(module / entry),
                    f"{module / entry}: the module's root holds only {ROOT_ENTRIES} and "
                    "the sharedPackages of addon.pkl",
                )

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
    def files(workspace: Workspace, module: Path) -> Iterable[Finding]:
        manifest = module / "MODULE.bazel"
        for relative in REQUIRED:
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
        path = (module / ".bazelrc").as_posix()
        if path in workspace.file_set and IMPORT not in workspace.text(path).splitlines():
            yield Finding(at(path), f"must import the shared settings: {IMPORT}")

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
        workspace: Workspace, module: Path, builds_apps: bool
    ) -> Iterable[Finding]:
        """
        The module's example projects in the root module: examples/addons/<module>/ itself, or
        each of its subdirectories with a project.
        """
        root = examples_path(module.name)
        projects = example_projects(root, workspace.configured)
        builds = sorted(
            project / build
            for project in projects
            for build in BUILD_FILES
            if (project / build).as_posix() in workspace.file_set
        )
        if not builds:
            yield Finding(
                at(module / "MODULE.bazel"), f"needs an example project in {root}"
            )
        targets = set(PROJECT_TARGETS) | ({APP_TARGET} if builds_apps else set())
        for build in builds:
            text = workspace.text(build.as_posix())
            for target in sorted(targets - set(NAME.findall(text))):
                yield Finding(at(build), f"example project must define :{target}")

    @staticmethod
    def extensions(workspace: Workspace, modules: list[Path]) -> Iterable[Finding]:
        """Extension names are unique across modules: on iOS they name the frameworks."""
        for extension, owning in sorted(extension_owners(workspace, modules).items()):
            for build in owning[1:]:
                yield Finding(
                    at(build), f"extension name {extension} is taken by {owning[0]}"
                )
