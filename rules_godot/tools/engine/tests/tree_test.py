import errno
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.engine import tree, tree_link
from tools.engine.tests.source_files import write_tree

UPSTREAM_CLASS_DB = (
    "#pragma once\n"
    "#define GD_IS_CLASS_ENABLED(m_class) is_class_enabled_v<m_class>\n\n"
    '#include "core/disabled_classes.gen.h" // IWYU pragma: keep.\n'
    "#define GDREGISTER_CLASS(m_class) if constexpr (GD_IS_CLASS_ENABLED(m_class)) {}\n"
)


class PrepareTest(unittest.TestCase):
    def test_class_db_includes_the_profile_only_where_it_is_declared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tree(root, {"core/object/class_db.h": UPSTREAM_CLASS_DB})
            tree.prepare(root)
            text = (root / "core/object/class_db.h").read_text()
            self.assertIn("#ifdef GODOT_DECLARES_BUILD_PROFILE", text)
            # Without the profile, evaluating a class's state names an undeclared identifier.
            self.assertIn(
                "#define GD_IS_CLASS_ENABLED(m_class) "
                "GODOT_BUILD_PROFILE_NOT_DECLARED_FOR_##m_class",
                text,
            )
            self.assertTrue(tree.is_scoped(root))

    def test_a_fork_that_changed_class_db_keeps_the_profile_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = UPSTREAM_CLASS_DB.replace("// IWYU pragma: keep.", "")
            write_tree(root, {"core/object/class_db.h": changed})
            tree.prepare(root)
            self.assertEqual((root / "core/object/class_db.h").read_text(), changed)
            self.assertFalse(tree.is_scoped(root))

    def test_the_shared_files_become_read_only(self) -> None:
        # A configuration that wrote through a recipe's link would change every recipe's
        # sources; the write fails instead.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tree(
                root, {"core/object/class_db.h": UPSTREAM_CLASS_DB, "SConstruct": ""}
            )
            tree.prepare(root)
            for name in ["core/object/class_db.h", "SConstruct"]:
                mode = (root / name).stat().st_mode
                self.assertFalse(
                    mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH), name
                )
            # Directories stay writable, so Bazel can delete the tree.
            self.assertTrue((root / "core").stat().st_mode & stat.S_IWUSR)


class DigestTest(unittest.TestCase):
    def test_the_digest_follows_every_path_and_content(self) -> None:
        # Recipes read the digest, so whatever changes the tree prepares them again.
        def digest(files: dict[str, str]) -> str:
            with tempfile.TemporaryDirectory() as directory:
                write_tree(Path(directory), files)
                return tree.prepare(Path(directory))

        base = {"SConstruct": "a", "core/object/class_db.h": UPSTREAM_CLASS_DB}
        self.assertEqual(digest(base), digest(dict(base)))
        self.assertNotEqual(digest(base), digest(base | {"SConstruct": "b"}))
        self.assertNotEqual(digest(base), digest(base | {"methods.py": "a"}))


class LinkTest(unittest.TestCase):
    def _tree(self, directory: str) -> Path:
        shared = Path(directory) / "tree"
        write_tree(
            shared,
            {
                "SConstruct": "# SConstruct\n",
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

    def test_a_recipe_shares_the_trees_files_and_owns_its_directories(self) -> None:
        # Godot's build scripts resolve paths, so the recipe's sources are no symbolic
        # links: they are the tree's files under a second name, and the directories,
        # where a configuration writes, are the recipe's own.
        with tempfile.TemporaryDirectory() as directory:
            shared = self._tree(directory)
            recipe = Path(directory) / "recipe"
            recipe.mkdir()
            tree_link.link(shared, recipe)
            for name in [
                "SConstruct",
                "core/object/class_db.h",
                "_scons/SCons/__init__.py",
            ]:
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

    def test_a_recipe_can_take_one_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shared = self._tree(directory)
            recipe = Path(directory) / "shell"
            recipe.mkdir()
            tree_link.link(shared, recipe, "platform/android/java/lib")
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
            recipe = Path(directory) / "recipe"
            recipe.mkdir()
            with mock.patch("os.link", side_effect=OSError(errno.EXDEV, "cross-device")):
                tree_link.link(shared, recipe)
            self.assertFalse(
                os.path.samefile(recipe / "SConstruct", shared / "SConstruct")
            )
            self.assertEqual((recipe / "SConstruct").read_text(), "# SConstruct\n")


if __name__ == "__main__":
    unittest.main()
