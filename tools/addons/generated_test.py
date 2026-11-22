"""addons/consumers.pkl follows the modules that override an add-on module."""

from tools.addons.generated import PATH, stale, write
from tools.addons.new import generate
from tools.addons.test_support import RepositoryTestCase


class GeneratedTest(RepositoryTestCase):
    def test_consumers_are_the_modules_that_override_an_add_on_module(self) -> None:
        generate("widget", root=self.root)
        (self.root / ".bazelignore").write_text("addons\ntests\n")
        (self.root / "tests").mkdir()
        (self.root / "tests/MODULE.bazel").write_text(
            'local_path_override(module_name = "autoload_widget", '
            'path = "../addons/widget")\n'
        )
        self.assertTrue(stale(self.root))
        write(self.root)
        self.assertFalse(stale(self.root))
        self.assertIn('["widget"] = List("tests")', (self.root / PATH).read_text())

    def test_a_new_module_leaves_the_file_current(self) -> None:
        write(self.root)
        generate("widget", root=self.root)
        self.assertFalse(stale(self.root))
