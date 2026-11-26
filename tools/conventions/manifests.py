"""The add-on modules' addon.pkl, as Pkl evaluates them, for the rules that read them."""

import functools
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import MappingProxyType

from tools.addons.modules import addon_manifest
from tools.conventions.context import Workspace
from tools.pkl.evaluate import PklError
from tools.setup.modules import is_addon_module

type Manifest = dict[str, tuple[str, ...]]


def module_manifest(workspace: Workspace, module: Path) -> Manifest | None:
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


@functools.cache
def module_manifests(workspace: Workspace) -> Mapping[Path, Manifest | None]:
    """
    Each add-on module's manifest, as module_manifest reads it, by module: they evaluate at
    once, since each runs the Pkl CLI.
    """
    modules = sorted(filter(is_addon_module, workspace.module_paths))
    with ThreadPoolExecutor() as pool:
        manifests = pool.map(lambda module: module_manifest(workspace, module), modules)
        return MappingProxyType(dict(zip(modules, manifests, strict=True)))
