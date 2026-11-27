"""Regressions for the registry test modules of the released modules."""

import unittest

from tools.conventions.rules.registry_test_module_in_bcr import RegistryTestModules
from tools.conventions.test_support import RepositoryTest

PRESUBMIT = 'bcr_test_module:\n  module_path: "bcr/smoke"\n'


class RegistryTestModulesTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        for module, templates in (
            ("rules_godot", ".bcr/rules_godot"),
            ("addons/widget", ".bcr/addons/widget"),
        ):
            self.write(f"{module}/MODULE.bazel", "")
            self.write(f"{module}/.bazelignore", "bcr\n")
            self.write(f"{templates}/presubmit.yml", PRESUBMIT)
            self.write(f"{module}/bcr/smoke/MODULE.bazel", "")
            self.write(f"{module}/bcr/smoke/BUILD.bazel", "")
            self.write(f"{module}/bcr/smoke/project.godot", "")

    def findings(self) -> list[str]:
        return [
            f"{item.location.path}: {item.message}"
            for item in RegistryTestModules().evaluate(self.context())
        ]

    def test_registry_test_modules_in_bcr_pass(self) -> None:
        self.assertEqual(self.findings(), [])

    def test_a_presubmit_without_a_test_module_is_reported(self) -> None:
        self.write(".bcr/addons/widget/presubmit.yml", "tasks:\n  verify_targets: {}\n")
        self.assertEqual(len(self.findings()), 1)
        self.assertIn("bcr_test_module", self.findings()[0])

    def test_the_test_module_lives_in_bcr(self) -> None:
        self.write(
            ".bcr/rules_godot/presubmit.yml",
            'bcr_test_module:\n  module_path: "e2e/smoke"\n',
        )
        self.write("rules_godot/e2e/smoke/MODULE.bazel", "")
        self.assertIn("rules_godot/", self.findings()[0])
        self.assertIn("bcr/<name>", self.findings()[0])

    def test_the_named_test_module_exists(self) -> None:
        self.write(
            ".bcr/addons/widget/presubmit.yml",
            'bcr_test_module:\n  module_path: "bcr/other"\n',
        )
        self.assertIn("addons/widget/bcr/other", self.findings()[0])

    def test_the_module_ignores_its_test_modules(self) -> None:
        self.write("addons/widget/.bazelignore", "")
        self.assertEqual(
            self.findings(),
            ["addons/widget/.bazelignore: must list bcr, the registry test modules"],
        )


if __name__ == "__main__":
    unittest.main()
