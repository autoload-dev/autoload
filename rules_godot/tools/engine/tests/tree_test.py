import stat
import tempfile
import unittest
from pathlib import Path

from tools.engine import tree
from tools.engine.tests.source_files import UPSTREAM_CLASS_DB, write_tree

_WRITABLE = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


class PrepareTest(unittest.TestCase):
    def test_the_tree_keeps_the_archives_files(self) -> None:
        # The tree is the upstream archive: engines of one source share it, so nothing
        # one engine's recipes change, such as class_db.h's scoping, happens here.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tree(root, {"core/object/class_db.h": UPSTREAM_CLASS_DB})
            tree.prepare(root)
            self.assertEqual(
                (root / "core/object/class_db.h").read_text(), UPSTREAM_CLASS_DB
            )

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
                self.assertFalse((root / name).stat().st_mode & _WRITABLE, name)
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


if __name__ == "__main__":
    unittest.main()
