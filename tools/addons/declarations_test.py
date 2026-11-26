import unittest

from tools.addons import declarations
from tools.addons.new import generate
from tools.addons.test_support import RepositoryTestCase


class DeclarationsTest(RepositoryTestCase):
    def test_each_add_on_module_is_declared_once_by_its_own_name(self) -> None:
        generate("widget", root=self.root, release=False)
        generate("gadget", root=self.root, release=False)
        text = declarations.segment(declarations.modules(self.root))
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
            [
                self.root / declarations.SEGMENT,
                self.root / declarations.REPOSITORIES,
                self.root / declarations.TARGETS,
            ],
            written,
        )
        self.assertIn(
            'ADDON_REPOSITORIES = [\n    "@autoload_widget",\n]\n',
            (self.root / declarations.REPOSITORIES).read_text(),
        )

    def test_the_root_targets_are_its_own_and_those_of_the_segment(self) -> None:
        generate("widget", root=self.root, release=False)
        generate("gadget", root=self.root, release=False)
        declarations.write(self.root)
        lines = (self.root / declarations.TARGETS).read_text().splitlines()
        patterns = [line for line in lines if line and not line.startswith("#")]
        self.assertEqual(
            ["//...", "@autoload_gadget//...", "@autoload_widget//..."], patterns
        )

    def test_a_module_s_version_is_left_to_its_override(self) -> None:
        generate("widget", root=self.root, release=False)
        manifest = self.root / "addons/widget/MODULE.bazel"
        before = declarations.segment(declarations.modules(self.root))
        manifest.write_text(manifest.read_text().replace('"0.1.0"', '"0.2.0"'))
        self.assertEqual(before, declarations.segment(declarations.modules(self.root)))


if __name__ == "__main__":
    unittest.main()
