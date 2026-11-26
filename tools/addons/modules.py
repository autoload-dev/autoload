"""The add-on modules of addons/ and what their own files say about them."""

from __future__ import annotations

import functools
import platform
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

from tools.pkl.evaluate import PklError, evaluate, manifest
from tools.setup.modules import (
    ADDON_E2E,
    ADDON_EXAMPLES,
    ADDONS,
    addon_modules,
    declarations,
    literals,
)

ROOT = Path(__file__).resolve().parents[2]
# The schema every addons/<module>/addon.pkl amends. Pkl evaluates each addon.pkl against it,
# with its defaults and types.
SCHEMA = Path(__file__).resolve().parent / "Addon.pkl"
# The line an addon.pkl starts with, after comments, relative to its module directory.
AMENDS = 'amends "../../tools/addons/Addon.pkl"'


@functools.cache
def choices() -> dict[str, tuple[str, ...]]:
    """The members of the schema's unions, such as the lanes CI runs and the desktops."""
    return {name: tuple(members) for name, members in evaluate(SCHEMA, "choices").items()}


def addon_manifest(path: Path) -> dict[str, tuple[str, ...]]:
    """
    An addon.pkl's properties, as Pkl evaluates it with the schema's defaults; one that does
    not amend the schema does not evaluate.
    """
    return {name: tuple(values) for name, values in manifest(path, AMENDS).items()}


def host() -> str:
    """This machine's operating system, as addon.pkl names desktop systems."""
    return {"Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system())


# The lanes that build applications: a module without them has no app and no Android SDK.
APP_LANES = ("android", "ios")


def builds_apps(lanes: tuple[str, ...] | list[str]) -> bool:
    """Whether a module with these lanes builds applications, and so has an app and SDK."""
    return not set(lanes).isdisjoint(APP_LANES)


def release_targets(lane: str, package: str) -> tuple[str, str]:
    """
    An application package's release build of a mobile lane and its debug symbols, which
    the package declares with examples/releases.bzl.
    """
    return (f"{package}:{lane}_release", f"{package}:{lane}_release.debug_symbols")


def module_attributes(manifest: str) -> dict[str, object]:
    """The literal attributes of a MODULE.bazel's module() declaration."""
    for declaration in declarations(manifest):
        if declaration.kind == "module":
            return literals(declaration.keywords)
    return {}


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


@dataclass(frozen=True)
class AddonModule:
    """One module `addons/<directory>`, read from its own files."""

    path: Path
    name: str
    projects: tuple[str, ...]
    desktops: tuple[str, ...] = field(default_factory=lambda: choices()["desktops"])
    lanes: tuple[str, ...] = field(default_factory=lambda: choices()["lanes"])
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
        try:
            manifest = addon_manifest(module / "addon.pkl")
        except (FileNotFoundError, PklError) as error:
            raise ValueError(
                f"{path}/addon.pkl: {error}; `aspect work conventions` says more"
            ) from error
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
            lanes=manifest["lanes"],
            test_operations=manifest["testOperations"],
            end_to_end=(root / e2e_path(path.name)).is_dir(),
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
