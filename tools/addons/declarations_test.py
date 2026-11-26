import unittest

from tools.addons import declarations
from tools.addons.new import generate
from tools.addons.test_support import RepositoryTestCase


class DeclarationsTest(RepositoryTestCase):
    def test_each_add_on_module_is_declared_once_by_its_own_name(self) -> None:
        generate("widget", root=self.root, release=False)
        generate("gadget", root=self.root, release=False)
        text = declarations.segment(self.root)
        self.assertTrue(text.startswith(declarations.HEADER))
        self.assertEqual(text.count("bazel_dep("), 2)
        self.assertIn(
            'bazel_dep(name = "autoload_widget", dev_dependency = True)',
            text,
        )

    def test_the_repositories_are_those_of_the_segment(self) -> None:
        generate("widget", root=self.root, release=False)
        written = declarations.write(self.root)
        self.assertEqual(
            [self.root / declarations.SEGMENT, self.root / declarations.REPOSITORIES],
            written,
        )
        self.assertIn(
            'ADDON_REPOSITORIES = [\n    "@autoload_widget",\n]\n',
            (self.root / declarations.REPOSITORIES).read_text(),
        )

    def test_a_module_s_version_is_left_to_its_override(self) -> None:
        generate("widget", root=self.root, release=False)
        manifest = self.root / "addons/widget/MODULE.bazel"
        before = declarations.segment(self.root)
        manifest.write_text(manifest.read_text().replace('"0.1.0"', '"0.2.0"'))
        self.assertEqual(before, declarations.segment(self.root))


if __name__ == "__main__":
    unittest.main()
