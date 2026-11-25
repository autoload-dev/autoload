"""The add-on modules of addons/ and what their own files say about them."""

from __future__ import annotations

import platform
import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from tools.setup.modules import (
    ADDON_E2E,
    ADDON_EXAMPLES,
    ADDONS,
    addon_modules,
    declarations,
    literals,
)

ROOT = Path(__file__).resolve().parents[2]
# The schema every addons/<module>/addon.pkl amends. This module applies its defaults but
# not its types, so RG015 checks the values against it.
SCHEMA = Path(__file__).resolve().parent / "Addon.pkl"
# The line an addon.pkl starts with, after comments, relative to its module directory.
AMENDS = 'amends "../../tools/addons/Addon.pkl"'
_LIST = re.compile(r"^(\w+)\s*(?::[^=]*)?=\s*List\(([^)]*)\)")
_ALIAS = re.compile(r"^typealias (\w+) = (.+)$")
_PROPERTY = re.compile(r"^(\w+):")


def addon_values(text: str) -> dict[str, list[str]]:
    """The `name = List(...)` properties of an addon.pkl, without its comments."""
    values = {}
    for line in text.splitlines():
        if (match := _LIST.match(line.split("//")[0].strip())) is not None:
            values[match[1]] = re.findall(r'"([^"]*)"', match[2])
    return values


def _schema_aliases(text: str) -> dict[str, tuple[str, ...]]:
    """The string union type aliases of the schema, such as Lane, with their members."""
    return {
        match[1]: tuple(re.findall(r'"([^"]*)"', match[2]))
        for line in text.splitlines()
        if (match := _ALIAS.match(line)) is not None
    }


_SCHEMA_TEXT = SCHEMA.read_text()
_ALIASES = _schema_aliases(_SCHEMA_TEXT)
# The lanes CI runs and the desktop systems of the desktop lane, as the schema names them.
LANES = _ALIASES["Lane"]
DESKTOPS = _ALIASES["Desktop"]
# What an addon.pkl may set, and the defaults of what it may leave out.
PROPERTIES = tuple(
    match[1]
    for line in _SCHEMA_TEXT.splitlines()
    if (match := _PROPERTY.match(line)) is not None
)
DEFAULTS = addon_values(_SCHEMA_TEXT)


def host() -> str:
    """This machine's operating system, as addon.pkl names desktop systems."""
    return {"Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system())


# The lanes that build applications: a module without them has no app and no Android SDK.
APP_LANES = ("android", "ios")


def builds_apps(lanes: tuple[str, ...] | list[str]) -> bool:
    """Whether a module with these lanes builds applications, and so has an app and SDK."""
    return not set(lanes).isdisjoint(APP_LANES)


def module_attributes(manifest: str) -> dict[str, object]:
    """The literal attributes of a MODULE.bazel's module() declaration."""
    for declaration in declarations(manifest):
        if declaration.kind == "module":
            return literals(declaration.keywords)
    return {}


def addon_manifest(text: str) -> dict[str, tuple[str, ...]]:
    """An addon.pkl's properties, with the schema's defaults for those it leaves out."""
    return {
        name: tuple(values)
        for name, values in (DEFAULTS | addon_values(text)).items()
        if name in PROPERTIES
    }


@dataclass(frozen=True)
class AddonModule:
    """One module `addons/<directory>`, read from its own files."""

    path: Path
    name: str
    projects: tuple[str, ...]
    desktops: tuple[str, ...] = DESKTOPS
    lanes: tuple[str, ...] = LANES
    test_operations: tuple[str, ...] = ()
    end_to_end: bool = False

    @property
    def directory(self) -> str:
        return self.path.name

    @property
    def builds_apps(self) -> bool:
        return builds_apps(self.lanes)

    @property
    def examples(self) -> Path:
        """The module's example applications in the root module, relative to the root."""
        return examples_path(self.directory)

    @property
    def tests(self) -> Path:
        """The module's end-to-end tests in the root module, relative to the root."""
        return e2e_path(self.directory)

    @property
    def package(self) -> str:
        """The package of the module's examples in the root module."""
        return f"//{self.examples.as_posix()}"

    def project_package(self, project: str) -> str:
        """The package of one example project: the examples' own, or a subdirectory's."""
        return self.package if project == "." else f"{self.package}/{project}"

    @classmethod
    def load(cls, path: Path, root: Path = ROOT) -> AddonModule:
        """Read the module at `path`, relative to the repository root."""
        module = root / path
        attributes = module_attributes((module / "MODULE.bazel").read_text())
        if "name" not in attributes:
            raise ValueError(f"{path}/MODULE.bazel: no module() name")
        addon = module / "addon.pkl"
        manifest = addon_manifest(addon.read_text() if addon.is_file() else "")
        examples = root / examples_path(path.name)
        configured = {p.parent for p in examples.glob("**/project.godot")}
        return cls(
            path=path,
            name=str(attributes["name"]),
            projects=tuple(
                project.relative_to(examples).as_posix()
                for project in example_projects(examples, configured)
            ),
            desktops=manifest["desktops"],
            lanes=manifest.get("lanes", LANES),
            test_operations=manifest["testOperations"],
            end_to_end=(root / e2e_path(path.name)).is_dir(),
        )


def examples_path(directory: str) -> Path:
    """The examples of the add-on module addons/<directory>, relative to the repository root."""
    return ADDON_EXAMPLES / directory


def e2e_path(directory: str) -> Path:
    """The end-to-end tests of the add-on module addons/<directory>, relative to the root."""
    return ADDON_E2E / directory


def example_projects(examples: Path, configured: Collection[Path]) -> tuple[Path, ...]:
    """
    A module's example projects, given the directories with a project.godot: the examples
    themselves when they are one project, else each subdirectory with a project.
    """
    if examples in configured:
        return (examples,)
    return tuple(sorted(d for d in configured if d.parent == examples))


def module_path(directory: str) -> Path:
    """An add-on module's directory, relative to the repository root."""
    return Path(ADDONS) / directory


def module_name(directory: str) -> str:
    """The Bazel module name of the add-on module addons/<directory>."""
    return f"autoload_{directory}"


def all_modules(root: Path = ROOT) -> tuple[AddonModule, ...]:
    """Every add-on module of the checkout, by directory."""
    return tuple(AddonModule.load(Path(path), root) for path in addon_modules(root))
