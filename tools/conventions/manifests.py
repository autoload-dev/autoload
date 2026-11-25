"""The add-on modules' addon.pkl, as Pkl evaluates them, for the rules that read them."""

from pathlib import Path

from tools.addons.modules import addon_manifest
from tools.conventions.context import Workspace
from tools.pkl.evaluate import PklError


def module_manifest(
    workspace: Workspace, module: Path
) -> dict[str, tuple[str, ...]] | None:
    """
    A module's addon.pkl, or None when it has none or it does not evaluate, which RG015
    reports.
    """
    path = module / "addon.pkl"
    if path.as_posix() not in workspace.file_set:
        return None
    try:
        return addon_manifest(workspace.root / path)
    except PklError:
        return None
