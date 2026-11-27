"""addon-modules-own-template-files: modules own their template files and registry templates."""

import unittest

from tools.conventions.rules.addon_modules_own_template_files import (
    AddonModulesOwnTemplateFiles,
)
from tools.conventions.test_support import AddonModuleTest


class AddonModulesOwnTemplateFilesTest(AddonModuleTest):
    rule = AddonModulesOwnTemplateFiles()

    def test_missing_template_files_are_reported(self) -> None:
        self.module("widget")
        self.files.discard(".bcr/addons/widget/presubmit.yml")
        self.files.discard("addons/widget/REPO.bazel")
        self.assertEqual(
            [
                "add-on module must own addons/widget/REPO.bazel",
                "add-on module must own .bcr/addons/widget/presubmit.yml",
            ],
            self.messages(),
        )


if __name__ == "__main__":
    unittest.main()
