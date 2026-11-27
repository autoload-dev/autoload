import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.engine import class_db, tree, tree_link
from tools.engine.patches import Patches
from tools.engine.tests.source_files import UPSTREAM_CLASS_DB, git_patch, write_tree

_VERSION_PATCH = git_patch(
    ("version.py", "version.py", '@@ -1 +1 @@\n-name = "Godot"\n+name = "Fork"\n')
)


class LinkTest(unittest.TestCase):
    def _tree(self, directory: str) -> Path:
        shared = Path(directory) / "tree"
        write_tree(
            shared,
            {
                "SConstruct": "# SConstruct\n",
                "version.py": 'name = "Godot"\n',
                "drivers/old.cpp": "int x;\n",
                "core/object/class_db.h": UPSTREAM_CLASS_DB,
                "platform/android/java/lib/AndroidManifest.xml": "<manifest/>\n",
                "_scons/SCons/__init__.py": "",
                "BUILD.bazel": "# the tree's own\n",
                "tree.json": "{}\n",
            },
        )
        (shared / "thirdparty").mkdir()
        (shared / "thirdparty/current").symlink_to("../core")
        tree.prepare(shared)
        return shared

    def _recipe(self, directory: str, name: str = "recipe") -> Path:
        recipe = Path(directory) / name
        recipe.mkdir()
        return recipe

    def test_a_recipe_shares_the_trees_files_and_owns_its_directories(self) -> None:
        # Godot's build scripts resolve paths, so the recipe's sources are no symbolic
        # links: they are the tree's files under a second name, and the directories,
        # where a configuration writes, are the recipe's own.
        with tempfile.TemporaryDirectory() as directory:
            shared = self._tree(directory)
            recipe = self._recipe(directory)
            tree_link.link(shared, recipe)
            for name in ["SConstruct", "_scons/SCons/__init__.py"]:
                self.assertFalse((recipe / name).is_symlink(), name)
                self.assertTrue(os.path.samefile(recipe / name, shared / name), name)
            for name in ["core", "core/object", "_scons"]:
                self.assertFalse((recipe / name).is_symlink(), name)
                self.assertNotEqual(
                    (recipe / name).stat().st_ino, (shared / name).stat().st_ino
                )
            self.assertEqual(os.readlink(recipe / "thirdparty/current"), "../core")
            # The tree's own repository files stay its own.
            for name in ["BUILD.bazel", "tree.json"]:
                self.assertFalse((recipe / name).exists(), name)

    def test_a_write_through_a_link_fails(self) -> None:
        # Every recipe of the source shares the linked file: a write into it would change
        # them all, so the tree's read-only files refuse it.
        with tempfile.TemporaryDirectory() as directory:
            shared = self._tree(directory)
            recipe = self._recipe(directory)
            tree_link.link(shared, recipe)
            with self.assertRaises(PermissionError):
                (recipe / "SConstruct").write_text("changed\n")
            self.assertEqual((shared / "SConstruct").read_text(), "# SConstruct\n")

    def test_a_recipe_owns_and_scopes_class_db(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shared = self._tree(directory)
            recipe = self._recipe(directory)
            tree_link.prepare(shared, recipe)
            self.assertFalse(
                os.path.samefile(recipe / class_db.CLASS_DB, shared / class_db.CLASS_DB)
            )
            self.assertTrue(class_db.is_scoped(recipe))
            self.assertFalse(class_db.is_scoped(shared))

    def test_a_recipe_patches_its_own_copies_of_the_touched_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shared = self._tree(directory)
            recipe = self._recipe(directory)
            patch = Path(directory) / "fork.patch"
            patch.write_text(
                _VERSION_PATCH
                + git_patch(
                    ("", "core/fork.h", "@@ -0,0 +1 @@\n+#pragma once\n"),
                    ("drivers/old.cpp", "", "@@ -1 +0,0 @@\n-int x;\n"),
                )
            )
            tree_link.prepare(shared, recipe, patches=Patches([patch]))
            self.assertEqual((recipe / "version.py").read_text(), 'name = "Fork"\n')
            self.assertEqual((recipe / "core/fork.h").read_text(), "#pragma once\n")
            # patch empties a deleted file or removes it, as its version does.
            deleted = recipe / "drivers/old.cpp"
            self.assertFalse(deleted.exists() and deleted.read_text())
            # The tree keeps upstream's files; every other file stays linked.
            self.assertEqual((shared / "version.py").read_text(), 'name = "Godot"\n')
            self.assertEqual((shared / "drivers/old.cpp").read_text(), "int x;\n")
            self.assertFalse((shared / "core/fork.h").exists())
            self.assertTrue(
                os.path.samefile(recipe / "SConstruct", shared / "SConstruct")
            )

    def test_class_db_is_scoped_after_the_patches(self) -> None:
        # A fork's patch of class_db.h applies to upstream's text, as before the tree
        # was shared.
        with tempfile.TemporaryDirectory() as directory:
            shared = self._tree(directory)
            recipe = self._recipe(directory)
            patch = Path(directory) / "class_db.patch"
            patch.write_text(
                git_patch(
                    (
                        "core/object/class_db.h",
                        "core/object/class_db.h",
                        (
                            "@@ -1,2 +1,3 @@\n #pragma once\n+// fork\n"
                            " #define GD_IS_CLASS_ENABLED(m_class) is_class_enabled_v<m_class>\n"
                        ),
                    )
                )
            )
            tree_link.prepare(shared, recipe, patches=Patches([patch]))
            text = (recipe / class_db.CLASS_DB).read_text()
            self.assertIn("// fork", text)
            self.assertTrue(class_db.is_scoped(recipe))

    def test_a_rejected_hunk_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shared = self._tree(directory)
            recipe = self._recipe(directory)
            patch = Path(directory) / "stale.patch"
            patch.write_text(_VERSION_PATCH.replace('-name = "Godot"', '-name = "Old"'))
            with self.assertRaisesRegex(SystemExit, "Error applying patch .*stale.patch"):
                tree_link.prepare(shared, recipe, patches=Patches([patch]))
            self.assertEqual((shared / "version.py").read_text(), 'name = "Godot"\n')

    def test_a_recipe_can_take_one_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shared = self._tree(directory)
            recipe = self._recipe(directory, "shell")
            tree_link.prepare(shared, recipe, "platform/android/java/lib")
            self.assertTrue(
                os.path.samefile(
                    recipe / "platform/android/java/lib/AndroidManifest.xml",
                    shared / "platform/android/java/lib/AndroidManifest.xml",
                )
            )
            self.assertEqual(sorted(path.name for path in recipe.iterdir()), ["platform"])

    def test_a_tree_on_another_file_system_is_copied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shared = self._tree(directory)
            recipe = self._recipe(directory)
            with mock.patch("os.link", side_effect=OSError(errno.EXDEV, "cross-device")):
                tree_link.link(shared, recipe)
            self.assertFalse(
                os.path.samefile(recipe / "SConstruct", shared / "SConstruct")
            )
            self.assertEqual((recipe / "SConstruct").read_text(), "# SConstruct\n")


if __name__ == "__main__":
    unittest.main()
