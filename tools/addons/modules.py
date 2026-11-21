"""The add-on modules of addons/ and what their own files say about them."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tools.setup.modules import ADDONS, addon_modules, declarations, literals

ROOT = Path(__file__).resolve().parents[2]
# What addon.pkl may name: the lanes hk.pkl runs and the hosts of the host lane.
LANES = ("host", "android", "ios")
HOSTS = ("linux", "macos")
_LIST = re.compile(r"^(\w+)\s*=\s*List\(([^)]*)\)\s*$")


def addon_values(text: str) -> dict[str, list[str]]:
    """The `name = List(...)` properties of an addon.pkl, without its comments."""
    values = {}
    for line in text.splitlines():
        if (match := _LIST.match(line.split("//")[0].strip())) is not None:
            values[match[1]] = re.findall(r'"([^"]*)"', match[2])
    return values


def module_attributes(manifest: str) -> dict[str, object]:
    """The literal attributes of a MODULE.bazel's module() declaration."""
    for declaration in declarations(manifest):
        if declaration.kind == "module":
            return literals(declaration.keywords)
    return {}


@dataclass(frozen=True)
class AddonModule:
    """One module `addons/<directory>`, read from its own files."""

    path: Path
    name: str
    version: str
    summary: str
    projects: tuple[str, ...]
    hosts: tuple[str, ...] = HOSTS

    @property
    def directory(self) -> str:
        return self.path.name

    @classmethod
    def load(cls, path: Path, root: Path = ROOT) -> AddonModule:
        """Read the module at `path`, relative to the repository root."""
        module = root / path
        attributes = module_attributes((module / "MODULE.bazel").read_text())
        if "name" not in attributes:
            raise ValueError(f"{path}/MODULE.bazel: no module() name")
        addon = module / "addon.pkl"
        hosts = addon_values(addon.read_text()).get("hosts") if addon.is_file() else None
        projects = (module / "examples" / "projects").glob("*/BUILD.bazel")
        return cls(
            path=path,
            name=str(attributes["name"]),
            version=str(attributes.get("version", "")),
            summary=readme_summary(module / "README.md"),
            projects=tuple(sorted(build.parent.name for build in projects)),
            hosts=tuple(hosts) if hosts else HOSTS,
        )


def readme_summary(readme: Path) -> str:
    """The first sentence of the paragraph after a README's title."""
    lines = readme.read_text().splitlines() if readme.is_file() else []
    title = next((i for i, line in enumerate(lines) if line.startswith("# ")), -1)
    paragraph: list[str] = []
    for line in lines[title + 1 :]:
        if line.strip():
            paragraph.append(line.strip())
        elif paragraph:
            break
    sentence, period, _ = " ".join(paragraph).partition(". ")
    return sentence + ("." if period else "")


def module_path(directory: str) -> Path:
    """An add-on module's directory, relative to the repository root."""
    return Path(ADDONS) / directory


def all_modules(root: Path = ROOT) -> tuple[AddonModule, ...]:
    """Every add-on module of the checkout, by directory."""
    return tuple(AddonModule.load(Path(path), root) for path in addon_modules(root))
