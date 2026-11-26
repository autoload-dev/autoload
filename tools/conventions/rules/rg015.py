"""RG015: add-on modules share one layout, and every add-on's backends live in native/."""

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tools.addons import registry as templates
from tools.addons.modules import (
    example_projects,
    examples_path,
    module_attributes,
    module_name,
)
from tools.addons.new import template_files
from tools.conventions.context import BUILD_FILES, Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.rules.rg023 import TESTS
from tools.setup.modules import ADDONS as ADDON_DIRECTORY
from tools.setup.modules import BCR, declarations, is_addon_module, literals

ADDONS = Path(ADDON_DIRECTORY)
# The files every module addons/<directory> owns: those of the generator's module template.
REQUIRED = tuple(relative for _, relative in template_files("module"))
# The registry templates each module owns in .bcr/addons/<directory>/, which the generator
# writes once with the module; publish-to-bcr reads them there.
REGISTRY = (*(relative for _, relative in template_files("bcr")), templates.METADATA)
# What a module's root holds besides its add-ons and the packages that other packages load
# by label: the template's files, its lock file and the directories every module may have.
ROOT_FILES = frozenset(
    {*(relative for relative in REQUIRED if "/" not in relative), "MODULE.bazel.lock"}
)
ROOT_DIRECTORIES = frozenset({"third_party", "tests", BCR})
ROOT_ENTRIES = ", ".join(
    ["its files", "its add-ons", *(f"{name}/" for name in sorted(ROOT_DIRECTORIES))]
)
STARLARK_FILES = ("BUILD", "BUILD.bazel", ".bzl", "MODULE.bazel")
# The shared settings each module's .bazelrc imports.
IMPORT = "import %workspace%/../module.bazelrc"
# The targets each example project defines. Its :app is not required: the release builds
# of examples/releases.bzl fail without it.
PROJECT_TARGETS = ("edit", "pack")
NAME = re.compile(r'\bname\s*=\s*"([^"]+)"')
EXTENSION = re.compile(r'godot_cc_extension\(\s*name\s*=\s*"([^"]+)"')


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


def allowed_entry(path: Path, is_file: bool, names: dict[str, set[str | None]]) -> bool:
    """
    Whether a root entry is a module file, a directory every module may have or an add-on,
    whose BUILD file declares a target named like its directory.
    """
    if is_file:
        return path.name in ROOT_FILES
    builds = ((path / build).as_posix() for build in BUILD_FILES)
    return path.name in ROOT_DIRECTORIES or any(
        path.name in names[build] for build in builds
    )


def names_package(value: str, labels: tuple[str, ...]) -> bool:
    """Whether a string is one of the labels or a label below them."""
    return any(
        value == label or value.startswith((f"{label}:", f"{label}/")) for label in labels
    )


def referenced_by_label(workspace: Workspace, module: Path, package: Path) -> bool:
    """
    Whether a Starlark file outside a package of the module's root names it by label: one of
    the module's other packages as `//<package>`, any other module as `@<module>//<package>`.
    """
    local = f"//{package.name}"
    remote = f"@{module_name(module.name)}{local}"
    for name in workspace.files:
        if not name.endswith(STARLARK_FILES) or Path(name).is_relative_to(package):
            continue
        labels = (local, remote) if workspace.owner(name) == module else (remote,)
        if any(names_package(s.value, labels) for s in workspace.strings(name)):
            return True
    return False


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


def starlark_files(workspace: Workspace, module: Path) -> list[str]:
    """
    The Starlark files of a module: its MODULE.bazel, BUILD and .bzl files and the build
    files of its third-party archives, without those of its nested modules.
    """
    prefix = f"{module.as_posix()}/"
    return [
        name
        for name in workspace.files
        if name.startswith(prefix)
        and name.endswith(STARLARK_FILES)
        and workspace.owner(name) == module
    ]


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
    label = f"@{repository}"
    uses = [
        Path(name)
        for name in files
        if any(
            literal.value == label or literal.value.startswith(f"{label}//")
            for literal in workspace.strings(name)
        )
    ]
    return bool(uses) and all(TESTS in use.parts for use in uses)


def tests_only_dependencies(workspace: Workspace, module: Path) -> list[str]:
    """The regular dependencies of a module that only its tests load from."""
    regular = regular_dependencies(workspace.text((module / "MODULE.bazel").as_posix()))
    files = starlark_files(workspace, module)
    return sorted(name for name in regular if only_tests_load(workspace, files, name))


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
            yield from self.module(workspace, module, names)
        yield from self.extensions(workspace, modules)
        yield from self.orphaned_templates(workspace, modules)

    def module(
        self, workspace: Workspace, module: Path, names: dict[str, set[str | None]]
    ) -> Iterable[Finding]:
        """The findings of one module."""
        yield from self.files(workspace, module)
        yield from self.registry(workspace, module)
        yield from self.imports(workspace, module)
        yield from self.root_entries(workspace, module, names)
        yield from self.projects(workspace, module)
        for name in tests_only_dependencies(workspace, module):
            yield Finding(
                at(module / "MODULE.bazel"),
                f"only tests load {name}, which every consumer inherits: "
                f"test with it from e2e/addons/{module.name}/",
            )

    @staticmethod
    def root_entries(
        workspace: Workspace,
        module: Path,
        names: dict[str, set[str | None]],
    ) -> Iterable[Finding]:
        """
        The entries of the module's root that are none of its files, add-ons, packages
        that other packages load by label or the directories every module may have.
        """
        for entry, is_file in sorted(module_root_entries(workspace, module).items()):
            path = module / entry
            if allowed_entry(path, is_file, names):
                continue
            if not is_file and referenced_by_label(workspace, module, path):
                continue
            yield Finding(
                at(path),
                f"{path}: the module's root holds only {ROOT_ENTRIES} and packages "
                "that other packages load by label",
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
    def projects(workspace: Workspace, module: Path) -> Iterable[Finding]:
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
        for build in builds:
            text = workspace.text(build.as_posix())
            for target in sorted(set(PROJECT_TARGETS) - set(NAME.findall(text))):
                yield Finding(at(build), f"example project must define :{target}")

    @staticmethod
    def extensions(workspace: Workspace, modules: list[Path]) -> Iterable[Finding]:
        """Extension names are unique across modules: on iOS they name the frameworks."""
        for extension, owning in sorted(extension_owners(workspace, modules).items()):
            for build in owning[1:]:
                yield Finding(
                    at(build), f"extension name {extension} is taken by {owning[0]}"
                )
