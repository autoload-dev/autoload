"""The add-on modules of addons/ and what their own files say about them."""

from __future__ import annotations

import platform
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from tools.pkl.evaluate import manifest
from tools.setup.modules import ADDON_EXAMPLES, ADDONS, declarations, literals

ROOT = Path(__file__).resolve().parents[2]
# The schema every addons/<module>/addon.pkl amends. Pkl evaluates each addon.pkl against it,
# with its defaults and types.
SCHEMA = Path(__file__).resolve().parent / "Addon.pkl"
# The line an addon.pkl starts with, after comments, relative to its module directory.
AMENDS = 'amends "../../tools/addons/Addon.pkl"'


@dataclass(frozen=True)
class AddonManifest:
    """What an addon.pkl declares, as Pkl evaluates it with the schema's defaults."""

    apps: bool
    test_operations: tuple[str, ...]
    shared_packages: tuple[str, ...]
    test_dependencies: tuple[str, ...]


def addon_manifest(path: Path) -> AddonManifest:
    """An addon.pkl's properties; one that does not amend the schema does not evaluate."""
    value = manifest(path, AMENDS)
    return AddonManifest(
        apps=bool(value["apps"]),
        test_operations=tuple(value["testOperations"]),
        shared_packages=tuple(value["sharedPackages"]),
        test_dependencies=tuple(value["testDependencies"]),
    )


def host() -> str:
    """This machine's operating system: `linux` or `macos`, as CI's jobs name it."""
    return {"Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system())


def module_attributes(manifest: str) -> dict[str, object]:
    """The literal attributes of a MODULE.bazel's module() declaration."""
    for declaration in declarations(manifest):
        if declaration.kind == "module":
            return literals(declaration.keywords)
    return {}


def examples_path(directory: str) -> Path:
    """The examples of the add-on module addons/<directory>, relative to the repository root."""
    return ADDON_EXAMPLES / directory


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
