"""RG015: add-on modules share one layout, and every add-on's backends live in native/."""

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
from tools.addons.new import REGISTRY_FILES, template_files
from tools.conventions.context import BUILD_FILES, Call, Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.rules.rg023 import TESTS
from tools.setup.modules import BCR, declarations, is_addon_module, literals

# The files every module addons/<directory> owns: those of the generator's module template.
REQUIRED = tuple(relative for _, relative in template_files("module"))
# What a module's root holds besides its add-ons and the packages that other packages load
# by label: the template's files, its lock file and the directories every module may have.
ROOT_FILES = frozenset(
    {*(relative for relative in REQUIRED if "/" not in relative), "MODULE.bazel.lock"}
)
ROOT_DIRECTORIES = frozenset({"third_party", "tests", BCR})
ROOT_ENTRIES = ", ".join(
    ["its files", "its add-ons", *(f"{name}/" for name in sorted(ROOT_DIRECTORIES))]
)
# The targets each example project defines.
PROJECT_TARGETS = ("edit", "pack")
# The rule of an add-on's extension, whose name names its framework on iOS.
EXTENSION = "godot_cc_extension"


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


def declared_calls(context: Context) -> frozenset[Call]:
    """The parsed calls of every BUILD file."""
    return frozenset(
        call
        for module in context.workspace.modules
        for call in context.starlark.calls(module)
    )


def declared_names(calls: Iterable[Call]) -> dict[str, set[str | None]]:
    """
    The names of the targets that each BUILD file declares by name; None stands for a name
    that is no literal. Calls without a name, such as package(), declare none.
    """
    names: dict[str, set[str | None]] = defaultdict(set)
    for call in calls:
        if "name" in call.attrs:
            names[call.location.path].add(call.literal_name)
    return names


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
    names: dict[str, set[str | None]],
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
    return any(name in names[build] for build in package) or (
        bool(package) and referenced_by_label(workspace, module, path)
    )


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


def extension_owners(
    calls: Iterable[Call], modules: list[Path]
) -> dict[str | None, list[Call]]:
    """The calls in the modules that declare each extension, by name, in file order."""
    owners: dict[str | None, list[Call]] = defaultdict(list)
    extensions = (
        call
        for call in calls
        if call.kind == EXTENSION and in_modules(call.location.path, modules)
    )
    for call in sorted(extensions, key=lambda c: (c.location.path, c.location.line)):
        owners[call.literal_name].append(call)
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
        and is_starlark(name)
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


class AddonModuleLayout:
    info = RuleInfo(
        "RG015",
        "Add-on modules share one layout",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        yield from self.backends(workspace)
        modules = sorted(filter(is_addon_module, workspace.module_paths))
        calls = declared_calls(context)
        names = declared_names(calls)
        for module in modules:
            yield from self.module(workspace, module, names)
        yield from self.extensions(calls, modules)
        yield from self.orphaned_templates(workspace, modules)

    def module(
        self, workspace: Workspace, module: Path, names: dict[str, set[str | None]]
    ) -> Iterable[Finding]:
        """The findings of one module."""
        yield from self.files(workspace, module)
        yield from self.registry(workspace, module)
        yield from self.root_entries(workspace, module, names)
        yield from self.projects(workspace, module, names)
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
        for entry in sorted(module_root_entries(workspace, module).items()):
            if not allowed_entry(workspace, module, entry, names):
                path = module / entry[0]
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
        """
        The module's registry templates exist; the file lint compares their contents
        (shared-module-files).
        """
        directory = templates.templates_directory(module.name)
        for name in REGISTRY_FILES:
            path = (directory / name).as_posix()
            if path not in workspace.file_set:
                yield Finding(
                    at(module / "MODULE.bazel"), f"add-on module must own {path}"
                )

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
    def projects(
        workspace: Workspace, module: Path, names: dict[str, set[str | None]]
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
        for build in builds:
            declared = names[build.as_posix()]
            missing = sorted(set(PROJECT_TARGETS) - declared)
            if missing and None in declared:
                yield Finding(
                    at(build),
                    f"cannot read every target name of {build.parent.as_posix()}",
                    "not_checked",
                )
                continue
            for target in missing:
                yield Finding(at(build), f"example project must define :{target}")

    @staticmethod
    def extensions(calls: Iterable[Call], modules: list[Path]) -> Iterable[Finding]:
        """Extension names are unique across modules: on iOS they name the frameworks."""
        owners = extension_owners(calls, modules)
        for call in owners.pop(None, []):
            yield Finding(
                call.location, f"cannot read the name of this {EXTENSION}", "not_checked"
            )
        for extension, owning in sorted(owners.items()):
            first = owning[0].location.path
            for call in owning[1:]:
                yield Finding(
                    call.location, f"extension name {extension} is taken by {first}"
                )
