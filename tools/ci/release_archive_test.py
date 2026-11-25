"""The release archive test runs each module's registry test module from its archive."""

import tempfile
import unittest
from pathlib import Path

from tools.ci.release_archive import archive, command, test_module


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
        root, base = Path("/repo"), Path("/tmp/base")
        self.assertEqual(
            command("rules_godot", base, root),
            ["bazel", "--output_base=/tmp/base", "test", "//..."],
        )
        self.assertIn(
            "--override_module=autoload_rules_godot=/repo/rules_godot",
            command("addons/widget", base, root),
        )

    def test_the_archive_is_the_release_archive(self) -> None:
        # The arguments of .github/workflows/release_prep.sh.
        self.assertEqual(
            archive("addons/widget", "autoload_widget-v1.0.0")[2:],
            [
                "--format=tar",
                "--prefix=release/",
                "--add-file=LICENSE",
                "autoload_widget-v1.0.0:addons/widget",
            ],
        )


if __name__ == "__main__":
    unittest.main()
