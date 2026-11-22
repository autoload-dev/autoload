"""The add-on modules of addons/ and what their own files say about them."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from tools.setup.modules import (
    ADDONS,
    addon_modules,
    declarations,
    literals,
    module_paths,
)

ROOT = Path(__file__).resolve().parents[2]
# The schema every addons/<module>/addon.pkl amends. hk's Pkl evaluator applies its defaults
# but not its types, so RG015 checks the values against it.
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
# The lanes hk.pkl runs and the hosts of the host lane, as the schema names them.
LANES = _ALIASES["Lane"]
HOSTS = _ALIASES["Host"]
# What an addon.pkl may set, and the defaults of what it may leave out.
PROPERTIES = tuple(
    match[1]
    for line in _SCHEMA_TEXT.splitlines()
    if (match := _PROPERTY.match(line)) is not None
)
DEFAULTS = addon_values(_SCHEMA_TEXT)
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
    hosts: tuple[str, ...] = HOSTS
    lanes: tuple[str, ...] = LANES
    test_operations: tuple[str, ...] = ()

    @property
    def directory(self) -> str:
        return self.path.name

    @property
    def builds_apps(self) -> bool:
        return builds_apps(self.lanes)

    @classmethod
    def load(cls, path: Path, root: Path = ROOT) -> AddonModule:
        """Read the module at `path`, relative to the repository root."""
        module = root / path
        attributes = module_attributes((module / "MODULE.bazel").read_text())
        if "name" not in attributes:
            raise ValueError(f"{path}/MODULE.bazel: no module() name")
        addon = module / "addon.pkl"
        manifest = addon_manifest(addon.read_text() if addon.is_file() else "")
        projects = (module / "examples" / "projects").glob("*/BUILD.bazel")
        return cls(
            path=path,
            name=str(attributes["name"]),
            projects=tuple(sorted(build.parent.name for build in projects)),
            hosts=manifest["hosts"],
            lanes=manifest.get("lanes", LANES),
            test_operations=manifest["testOperations"],
        )


def module_path(directory: str) -> Path:
    """An add-on module's directory, relative to the repository root."""
    return Path(ADDONS) / directory


def module_name(directory: str) -> str:
    """The Bazel module name of the add-on module addons/<directory>."""
    return f"autoload_{directory}"


def all_modules(root: Path = ROOT) -> tuple[AddonModule, ...]:
    """Every add-on module of the checkout, by directory."""
    return tuple(AddonModule.load(Path(path), root) for path in addon_modules(root))


def consumers(root: Path = ROOT) -> dict[str, tuple[str, ...]]:
    """
    The modules of the checkout that use each add-on module through `local_path_override`,
    by the add-on module's directory: what Bazel builds of an add-on beyond its own lanes.
    A module's own examples are none.
    """
    users: dict[str, set[str]] = {}
    for consumer in module_paths(root):
        source = (root / consumer / "MODULE.bazel").read_text()
        for declaration in declarations(source):
            path = literals(declaration.keywords).get("path")
            if declaration.kind != "local_path_override" or not isinstance(path, str):
                continue
            target = Path(os.path.normpath(Path(consumer) / path))
            if target.parent == Path(ADDONS) and Path(consumer).parent != target:
                users.setdefault(target.name, set()).add(consumer)
    return {name: tuple(sorted(users[name])) for name in sorted(users)}
