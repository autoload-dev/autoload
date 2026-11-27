"""registry-templates-have-their-module: registry templates belong to an existing module."""

import unittest

from tools.conventions.rules.registry_templates_have_their_module import (
    RegistryTemplatesHaveTheirModule,
)
from tools.conventions.test_support import AddonModuleTest


class RegistryTemplatesHaveTheirModuleTest(AddonModuleTest):
    rule = RegistryTemplatesHaveTheirModule()

    def test_registry_templates_of_a_removed_module(self) -> None:
        self.write(".bcr/addons/gone/source.template.json", "{}\n")
        self.assertEqual(["no add-on module owns .bcr/addons/gone"], self.messages())


if __name__ == "__main__":
    unittest.main()
