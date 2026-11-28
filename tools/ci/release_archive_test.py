"""The release archive test runs each module's registry test module from its archive."""

import tempfile
import unittest
from pathlib import Path

from tools.ci.release_archive import (
    archive,
    command,
    in_place,
    test_module,
    workspace,
)


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
                "autoload_widget-v1.0.0:addons/widget",
            ],
        )

    def test_a_release_uses_the_ruleset_its_module_declares(self) -> None:
        released = command(
            "addons/widget", Path("/tmp/base"), Path("/repo"), registry=True
        )
        self.assertFalse(any(a.startswith("--override_module") for a in released))

    def test_in_place_runs_the_test_module_in_the_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            presubmit = root / ".bcr/addons/widget/presubmit.yml"
            presubmit.parent.mkdir(parents=True)
            presubmit.write_text('bcr_test_module:\n  module_path: "bcr/smoke"\n')
            # The test module's own settings (addons/bcr.bazelrc) name the checkout's
            # ruleset, and its server stays up for the next run.
            self.assertEqual(
                in_place("addons/widget", root),
                (root / "addons/widget/bcr/smoke", ["bazel", "test", "//..."]),
            )

    def test_each_checkout_extracts_to_a_directory_of_its_own(self) -> None:
        self.assertNotEqual(
            workspace("addons/widget", Path("/a")), workspace("addons/widget", Path("/b"))
        )


if __name__ == "__main__":
    unittest.main()
