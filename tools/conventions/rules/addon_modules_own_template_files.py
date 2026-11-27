"""
addon-modules-own-template-files: every add-on module owns the files of the generator's
module template and its registry templates in .bcr/addons/<module>/.
"""

from collections.abc import Iterable

from tools.addons import registry
from tools.addons.new import REGISTRY_FILES
from tools.conventions.addon_modules import MODULE_FILES, addon_module_paths, at
from tools.conventions.context import Context
from tools.conventions.framework import Finding, RuleInfo


class AddonModulesOwnTemplateFiles:
    info = RuleInfo(
        "addon-modules-own-template-files",
        "Add-on modules own the files of the generator's template",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        for module in addon_module_paths(workspace):
            templates = registry.templates_directory(module.name)
            owned = [module / relative for relative in MODULE_FILES] + [
                templates / name for name in REGISTRY_FILES
            ]
            for path in owned:
                if path.as_posix() not in workspace.file_set:
                    yield Finding(
                        at(module / "MODULE.bazel"),
                        f"add-on module must own {path.as_posix()}",
                    )
