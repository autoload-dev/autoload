"""Check independent module discovery and safe maintenance of generated pages."""

import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools.docs.api_docs import (
    documented_target,
    inventory_errors,
    reference_errors,
    update_reference,
)


def inventory() -> dict[str, Any]:
    return {
        "PUBLIC_APIS": {},
        "CROSS_REPOSITORY_MODULES": {},
        "SUPPORT_MODULES": [],
    }


class InventoryTest(unittest.TestCase):
    def test_unlisted_module_is_rejected_independently_of_bazel_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "godot").mkdir()
            (root / "godot/new.bzl").write_text('"""New module."""\n')
            self.assertIn(
                "unclassified new module", inventory_errors(root, inventory())[0]
            )

    def test_white_box_test_files_have_no_module_role(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("godot/private/tests/x_test.bzl", "godot/tests/api/cases.bzl"):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text('"""White-box test."""\n')
            (root / "godot/testing").mkdir(parents=True)
            (root / "godot/testing/new.bzl").write_text('"""Test helper."""\n')
            errors = inventory_errors(root, inventory())
            self.assertEqual(1, len(errors), errors)
            self.assertIn("//godot/testing:new.bzl: unclassified new module", errors[0])

    def test_public_file_cannot_be_hidden_as_private_support(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "godot").mkdir()
            (root / "godot/new.bzl").write_text('"""New module."""\n')
            config = inventory()
            config["SUPPORT_MODULES"] = ["//godot:new.bzl"]
            self.assertTrue(
                any(
                    "support modules must be private" in error
                    for error in inventory_errors(root, config)
                )
            )

    def test_overlapping_roles_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "godot").mkdir()
            (root / "godot/helper.bzl").write_text('"""Helper."""\n')
            config = inventory()
            config["PUBLIC_APIS"]["//godot:helper.bzl"] = {
                "group": "Core",
                "purpose": "Build.",
                "symbols": ["helper"],
            }
            config["CROSS_REPOSITORY_MODULES"]["//godot:helper.bzl"] = "Internal helper."
            self.assertTrue(
                any(
                    "multiple module roles" in error
                    for error in inventory_errors(root, config)
                )
            )

    def test_support_modules_must_restrict_actual_load_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "godot/private").mkdir(parents=True)
            path = root / "godot/private/helper.bzl"
            config = inventory()
            config["SUPPORT_MODULES"] = ["//godot/private:helper.bzl"]
            path.write_text('"""Helper."""\n')
            self.assertTrue(
                any(
                    "explicit restricted load visibility" in error
                    for error in inventory_errors(root, config)
                )
            )
            path.write_text('"""Helper."""\nvisibility("public")\n')
            self.assertTrue(
                any(
                    "cannot have public load visibility" in error
                    for error in inventory_errors(root, config)
                )
            )
            path.write_text('"""Helper."""\nvisibility("//godot")\n')
            self.assertEqual(inventory_errors(root, config), [])

    def test_public_target_comparison_skips_private_and_test_packages(self) -> None:
        self.assertTrue(documented_target("//godot:variant"))
        self.assertTrue(documented_target("//godot/platforms:linux_x86_64"))
        self.assertFalse(documented_target("//godot/private:default_project"))
        self.assertFalse(documented_target("//godot/private/testing:inspect_ios_app"))
        self.assertFalse(documented_target("//godot/tests/api_contracts:pack"))
        self.assertFalse(documented_target("//godot/extension/tests:fixture"))

    def test_short_function_needs_documentation_and_return_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "godot").mkdir()
            (root / "godot/defs.bzl").write_text("def small(value):\n    return value\n")
            config = inventory()
            config["PUBLIC_APIS"]["//godot:defs.bzl"] = {
                "group": "Core",
                "purpose": "Build.",
                "symbols": ["small"],
            }
            errors = inventory_errors(root, config)
            self.assertTrue(any("docstring" in error for error in errors))
            self.assertTrue(any("Returns:" in error for error in errors))

    def test_generated_repository_modules_keep_cross_repository_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "godot/private").mkdir(parents=True)
            path = root / "godot/private/helper.bzl"
            config = inventory()
            config["CROSS_REPOSITORY_MODULES"]["//godot/private:helper.bzl"] = (
                "Loaded by generated BUILD files."
            )
            path.write_text('"""Implementation."""\nvisibility("private")\n')
            self.assertTrue(
                any(
                    "explicit public load visibility" in error
                    for error in inventory_errors(root, config)
                )
            )
            path.write_text('"""Implementation."""\nvisibility("public")\n')
            self.assertEqual(inventory_errors(root, config), [])

    def test_diff_finds_missing_and_obsolete_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for side in ("old", "new"):
                (root / side / "reference").mkdir(parents=True)
            (root / "old/reference/removed.md").write_text("old")
            (root / "new/reference/added.md").write_text("new")
            errors = reference_errors(root / "old", root / "new")
            self.assertTrue(any("Missing" in error for error in errors))
            self.assertTrue(any("Obsolete" in error for error in errors))

    def test_update_removes_owned_pages_but_preserves_unmarked_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for side in ("old", "new"):
                (root / side / "reference").mkdir(parents=True)
            stale = root / "old/reference/stale.md"
            stale.write_text("User-authored content")
            (root / "new/reference/current.md").write_text("New generated content")
            with self.assertRaisesRegex(ValueError, "Refusing to remove"):
                update_reference(root / "old", root / "new")
            self.assertEqual(stale.read_text(), "User-authored content")
            self.assertFalse((root / "old/reference/current.md").exists())
            stale.write_text("<!-- Generated with Stardoc: tool -->\nold")
            update_reference(root / "old", root / "new")
            self.assertFalse(stale.exists())
            self.assertEqual(
                (root / "old/reference/current.md").read_text(), "New generated content"
            )


if __name__ == "__main__":
    unittest.main()
