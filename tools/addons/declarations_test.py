"""The add-on modules' declarations in the root module."""

import unittest

from tools.addons import declarations
from tools.addons.new import generate
from tools.addons.test_support import RepositoryTestCase


class DeclarationsTest(RepositoryTestCase):
    def test_each_add_on_module_is_declared_once_from_its_own_manifest(self) -> None:
        generate("widget", root=self.root, release=False)
        generate("gadget", root=self.root, release=False)
        text = declarations.segment(self.root)
        self.assertTrue(text.startswith(declarations.HEADER))
        self.assertEqual(text.count("bazel_dep("), 2)
        self.assertIn(
            'bazel_dep(name = "autoload_widget", version = "0.1.0", dev_dependency = True)',
            text,
        )

    def test_a_segment_is_current_only_while_it_matches_the_modules(self) -> None:
        generate("widget", root=self.root, release=False)
        self.assertTrue(declarations.is_current(self.root))
        (self.root / declarations.SEGMENT).write_text(declarations.HEADER)
        self.assertFalse(declarations.is_current(self.root))


if __name__ == "__main__":
    unittest.main()
