"""
The templates publish-to-bcr reads for an add-on module's releases, `.bcr/addons/<directory>/`.

The generator (tools/addons/new.py) writes them once with the module, and the conventions
(RG015) check them: nothing regenerates them.
"""

import json
from collections.abc import Callable
from pathlib import Path

from tools.addons.modules import ROOT, module_name, module_path
from tools.setup.modules import RULESET

METADATA = "metadata.template.json"
SOURCE = "source.template.json"
# The ruleset's metadata template, whose maintainers and repositories every module shares.
RULESET_METADATA = Path(".bcr") / RULESET / METADATA


def templates_directory(directory: str) -> Path:
    """Where the templates of addons/<directory> lie, relative to the repository root."""
    return Path(".bcr") / module_path(directory)


def metadata(directory: str, root: Path = ROOT) -> str:
    """
    A module's metadata template: the ruleset's, so that maintainers and repositories have
    one source, with the module's directory as homepage.
    """
    values = json.loads((root / RULESET_METADATA).read_text())
    values["homepage"] += f"/tree/main/{module_path(directory).as_posix()}"
    return json.dumps(values, indent=2) + "\n"


def metadata_problem(text: str, directory: str, root: Path) -> str | None:
    if text == metadata(directory, root):
        return None
    return f"must be {RULESET_METADATA.as_posix()} with the module's homepage"


def source_problem(text: str, directory: str, root: Path) -> str | None:
    archive = f"{module_name(directory)}-{{VERSION}}"
    return None if archive in text else f"must release the archive {archive}"


# What each template must say about its module, by file name.
CHECKS: dict[str, Callable[[str, str, Path], str | None]] = {
    METADATA: metadata_problem,
    SOURCE: source_problem,
}


def problem(name: str, text: str, directory: str, root: Path = ROOT) -> str | None:
    """What is wrong with one of a module's templates, or None."""
    check = CHECKS.get(name)
    return check(text, directory, root) if check else None


def owner(path: str) -> str | None:
    """The module directory whose templates hold path, if any."""
    parts = Path(path).parts
    inside = parts[:2] == (".bcr", "addons") and len(parts) > 3
    return parts[2] if inside else None
