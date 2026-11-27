"""
shared-module-files-as-generated: add-on modules keep the shared files as the add-on
generator writes them.
"""

from collections.abc import Iterable
from pathlib import Path

from tools.addons import registry
from tools.addons.new import shared_files
from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo
from tools.setup.modules import ADDONS, addon_modules


def owner(name: str, modules: frozenset[str]) -> str | None:
    """The directory of the add-on module whose file or registry template name is, if any."""
    parts = Path(name).parts
    directory = registry.owner(name) or (parts[1] if parts[0] == ADDONS else None)
    return directory if f"{ADDONS}/{directory}" in modules else None


class SharedModuleFiles:
    info = RuleInfo(
        "shared-module-files-as-generated",
        "Add-on modules keep the shared files as the add-on generator writes them",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        modules = frozenset(addon_modules(workspace.root))
        expected: dict[str, dict[str, str]] = {}
        for name in workspace.files:
            directory = owner(name, modules)
            if directory is None:
                continue
            if directory not in expected:
                expected[directory] = {
                    path.as_posix(): text
                    for path, text in shared_files(directory, workspace.root).items()
                }
            text = expected[directory].get(name)
            if text is not None and workspace.text(name) != text:
                yield Finding(
                    Location(name, 1),
                    "differs from what the add-on generator writes; run `aspect generate`",
                )
