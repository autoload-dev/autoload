"""The add-on modules of addons/ and what their own files say about them."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from tools.setup.modules import addon_modules, declarations

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AddonModule:
    """One module `addons/<directory>`, read from its MODULE.bazel, README and examples."""

    path: Path
    name: str
    version: str
    title: str
    summary: str
    projects: tuple[str, ...]

    @property
    def directory(self) -> str:
        return self.path.name

    @classmethod
    def load(cls, path: Path, root: Path = ROOT) -> AddonModule:
        """Read the module at `path`, relative to the repository root."""
        module = root / path
        attributes = next(
            (
                {key: ast.literal_eval(value) for key, value in item.keywords.items()}
                for item in declarations((module / "MODULE.bazel").read_text())
                if item.kind == "module"
            ),
            None,
        )
        if attributes is None:
            raise ValueError(f"{path}/MODULE.bazel: no module() declaration")
        title, summary = readme_lead(module / "README.md")
        projects = tuple(
            sorted(
                build.parent.name
                for build in (module / "examples" / "projects").glob("*/BUILD.bazel")
            )
        )
        return cls(
            path=path,
            name=attributes["name"],
            version=attributes.get("version", ""),
            title=title,
            summary=summary,
            projects=projects,
        )


def readme_lead(readme: Path) -> tuple[str, str]:
    """A README's title and the first sentence of its first paragraph."""
    lines = readme.read_text().splitlines() if readme.is_file() else []
    title = next((line[2:].strip() for line in lines if line.startswith("# ")), "")
    paragraph: list[str] = []
    for line in lines[
        next((i for i, line in enumerate(lines) if line.startswith("# ")), 0) + 1 :
    ]:
        if line.strip():
            paragraph.append(line.strip())
        elif paragraph:
            break
    text = " ".join(paragraph)
    sentence, period, _ = text.partition(". ")
    return title, sentence + ("." if period else "")


def all_modules(root: Path = ROOT) -> tuple[AddonModule, ...]:
    """Every add-on module of the checkout, by directory."""
    return tuple(AddonModule.load(Path(path), root) for path in addon_modules(root))
