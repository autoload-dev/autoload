"""The release archive test runs each module's registry test module from its archive."""

import tempfile
import unittest
from pathlib import Path

from tools.ci.release_archive import command, test_module


class ReleaseArchiveTest(unittest.TestCase):
    def test_the_presubmit_names_the_test_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            presubmit = root / ".bcr/addons/widget/presubmit.yml"
            presubmit.parent.mkdir(parents=True)
            presubmit.write_text('bcr_test_module:\n  module_path: "bcr/smoke"\n')
            self.assertEqual(test_module("addons/widget", root), "bcr/smoke")
            presubmit.write_text("tasks: {}\n")
            with self.assertRaises(ValueError):
                test_module("addons/widget", root)

    def test_an_add_on_module_uses_the_checkout_s_ruleset(self) -> None:
        root = Path("/repo")
        self.assertEqual(command("rules_godot", root), ["bazel", "test", "//..."])
        self.assertEqual(
            command("addons/widget", root),
            [
                "bazel",
                "test",
                "--override_module=autoload_rules_godot=/repo/rules_godot",
                "//...",
            ],
        )


if __name__ == "__main__":
    unittest.main()
