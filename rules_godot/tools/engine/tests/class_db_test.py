import tempfile
import unittest
from pathlib import Path

from tools.engine import class_db
from tools.engine.tests.source_files import UPSTREAM_CLASS_DB, write_tree


class ClassDbTest(unittest.TestCase):
    def test_class_db_includes_the_profile_only_where_it_is_declared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tree(root, {"core/object/class_db.h": UPSTREAM_CLASS_DB})
            class_db.scope(root)
            text = (root / "core/object/class_db.h").read_text()
            self.assertIn("#ifdef GODOT_DECLARES_BUILD_PROFILE", text)
            # Without the profile, evaluating a class's state names an undeclared identifier.
            self.assertIn(
                "#define GD_IS_CLASS_ENABLED(m_class) "
                "GODOT_BUILD_PROFILE_NOT_DECLARED_FOR_##m_class",
                text,
            )
            self.assertTrue(class_db.is_scoped(root))

    def test_a_fork_that_changed_class_db_keeps_the_profile_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = UPSTREAM_CLASS_DB.replace("// IWYU pragma: keep.", "")
            write_tree(root, {"core/object/class_db.h": changed})
            class_db.scope(root)
            self.assertEqual((root / "core/object/class_db.h").read_text(), changed)
            self.assertFalse(class_db.is_scoped(root))


if __name__ == "__main__":
    unittest.main()
