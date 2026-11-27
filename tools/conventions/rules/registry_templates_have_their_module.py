"""
registry-templates-have-their-module: the registry templates in .bcr/addons/<module>/
belong to an existing add-on module and are removed with it.
"""

from collections.abc import Iterable

from tools.addons import registry
from tools.conventions.addon_modules import addon_module_paths, at
from tools.conventions.context import Context
from tools.conventions.framework import Finding, RuleInfo


class RegistryTemplatesHaveTheirModule:
    info = RuleInfo(
        "registry-templates-have-their-module",
        "Registry templates belong to an existing add-on module",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        modules = {module.name for module in addon_module_paths(workspace)}
        owners = {owner for name in workspace.files if (owner := registry.owner(name))}
        for directory in sorted(owners - modules):
            path = registry.templates_directory(directory)
            yield Finding(at(path), f"no add-on module owns {path.as_posix()}")
