"""addon-module-named-after-directory: addons/<module>/ is named autoload_<module>."""

import unittest

from tools.conventions.rules.addon_module_named_after_directory import (
    AddonModuleNamedAfterDirectory,
)
from tools.conventions.test_support import AddonModuleTest


class AddonModuleNamedAfterDirectoryTest(AddonModuleTest):
    rule = AddonModuleNamedAfterDirectory()

    def test_a_module_named_otherwise_is_reported(self) -> None:
        self.module("widget")
        self.write("addons/widget/MODULE.bazel", 'module(name = "widget")\n')
        self.assertEqual(["add-on module must be named autoload_widget"], self.messages())


if __name__ == "__main__":
    unittest.main()
