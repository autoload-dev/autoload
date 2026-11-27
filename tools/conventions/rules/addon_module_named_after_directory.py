"""
addon-module-named-after-directory: the module addons/<module>/ is named
autoload_<module>.
"""

from collections.abc import Iterable

from tools.addons.modules import module_attributes, module_name
from tools.conventions.addon_modules import addon_module_paths, at
from tools.conventions.context import Context
from tools.conventions.framework import Finding, RuleInfo


class AddonModuleNamedAfterDirectory:
    info = RuleInfo(
        "addon-module-named-after-directory",
        "The module addons/<module>/ is named autoload_<module>",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        for module in addon_module_paths(workspace):
            manifest = (module / "MODULE.bazel").as_posix()
            expected = module_name(module.name)
            if module_attributes(workspace.text(manifest)).get("name") != expected:
                yield Finding(at(manifest), f"add-on module must be named {expected}")
