"""What the add-on generator writes satisfies every add-on module rule."""

import unittest

from tools.conventions.registry import ADDON_MODULE_RULES
from tools.conventions.test_support import AddonModuleTest


class GeneratedModulesTest(AddonModuleTest):
    def test_generated_modules_satisfy_every_add_on_module_rule(self) -> None:
        self.module("widget")
        self.module("firebase", "core")
        self.module("firebase", "analytics")
        for rule in ADDON_MODULE_RULES:
            self.assertEqual([], self.messages(rule), rule.info.name)


if __name__ == "__main__":
    unittest.main()
