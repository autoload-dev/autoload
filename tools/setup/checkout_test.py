"""The checkout-shaped tree of the modules' files a test declares."""

import tempfile
import unittest
from pathlib import Path

from tools.setup import checkout
from tools.setup.modules import module_paths, registry_test_modules


class CheckoutTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = checkout.copy(Path(directory.name))

    def test_each_overridden_module_is_at_its_directory(self) -> None:
        overrides = dict(checkout.overrides(self.root))
        self.assertEqual("rules_godot", overrides["autoload_rules_godot"])
        self.assertEqual("addons/gdunit", overrides["autoload_gdunit"])
        self.assertLessEqual(
            {"rules_godot", "addons/gdunit"}, set(module_paths(self.root))
        )
        self.assertTrue((self.root / "rules_godot/.bazelversion").is_file())

    def test_the_registry_test_modules_come_with_their_module(self) -> None:
        self.assertIn("rules_godot/bcr/smoke", registry_test_modules(self.root))

    def test_the_copy_is_writable_and_leaves_the_runfiles_alone(self) -> None:
        manifest = self.root / "MODULE.bazel"
        text = manifest.read_text()
        manifest.write_text("changed")
        self.assertFalse(manifest.is_symlink())
        self.assertEqual(text, checkout.runfile("_main/MODULE.bazel").read_text())


if __name__ == "__main__":
    unittest.main()
