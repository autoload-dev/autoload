"""
The templates publish-to-bcr reads for an add-on module's releases, `.bcr/addons/<directory>/`.

The generator (tools/addons/new.py) writes them with the module, and `aspect generate` writes
them again (shared files, tools/addons/new.py).
"""

import json
import re
from pathlib import Path

from tools.addons.modules import ROOT, module_path
from tools.setup.modules import RULESET

METADATA = "metadata.template.json"
SOURCE = "source.template.json"
# The ruleset's metadata template, whose maintainers and repositories every module shares.
RULESET_METADATA = Path(".bcr") / RULESET / METADATA
PRESUBMIT = "presubmit.yml"
_MODULE_PATH = re.compile(r'^\s*module_path:\s*"?([^"\s]+)"?\s*$', re.MULTILINE)


def presubmit(module: Path) -> Path:
    """The presubmit.yml of a released module, the ruleset or addons/<directory>."""
    return Path(".bcr") / module / PRESUBMIT


def registry_test_module(presubmit_text: str) -> str | None:
    """The registry test module a presubmit.yml runs, relative to the module, if any."""
    if "bcr_test_module:" not in presubmit_text:
        return None
    match = _MODULE_PATH.search(presubmit_text)
    return match[1] if match else None


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


def owner(path: str) -> str | None:
    """The module directory whose templates hold path, if any."""
    parts = Path(path).parts
    inside = parts[:2] == (".bcr", "addons") and len(parts) > 3
    return parts[2] if inside else None
