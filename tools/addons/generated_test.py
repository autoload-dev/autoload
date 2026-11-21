"""The registry templates, its module roots and the README table follow the modules."""

import json

from tools.addons.generated import BEGIN, stale, write
from tools.addons.new import generate
from tools.addons.test_support import RepositoryTestCase


class GeneratedTest(RepositoryTestCase):
    def test_without_modules_only_the_ruleset_is_a_root(self) -> None:
        write(self.root)
        self.assertEqual(stale(self.root), [])
        self.assertIn(
            'moduleRoots:\n  - "."\n', (self.root / ".bcr/config.yml").read_text()
        )
        self.assertIn(
            "No add-on module yet", (self.root / "addons/README.md").read_text()
        )

    def test_a_new_module_makes_the_files_stale_until_they_are_written(self) -> None:
        write(self.root)
        generate("widget", root=self.root)
        (self.root / "addons/widget/README.md").write_text(
            "# Widget\n\nWidgets for Godot. More text.\n"
        )
        self.assertEqual(
            stale(self.root),
            [
                ".bcr/addons/widget/metadata.template.json",
                ".bcr/addons/widget/presubmit.yml",
                ".bcr/addons/widget/source.template.json",
                ".bcr/config.yml",
                "addons/README.md",
            ],
        )
        write(self.root)
        self.assertEqual(stale(self.root), [])
        source = json.loads(
            (self.root / ".bcr/addons/widget/source.template.json").read_text()
        )
        self.assertEqual(source["strip_prefix"], "autoload_widget-{VERSION}")
        metadata = json.loads(
            (self.root / ".bcr/addons/widget/metadata.template.json").read_text()
        )
        self.assertTrue(metadata["homepage"].endswith("/tree/main/addons/widget"))
        readme = (self.root / "addons/README.md").read_text()
        self.assertIn(
            "| [`autoload_widget`](widget) | Widgets for Godot. | 0.1.0 |", readme
        )
        self.assertEqual(readme.count(BEGIN), 1)

    def test_templates_of_a_removed_module_are_removed(self) -> None:
        generate("widget", root=self.root)
        write(self.root)
        for path in sorted((self.root / "addons/widget").rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        (self.root / "addons/widget").rmdir()
        self.assertIn(".bcr/addons/widget/presubmit.yml", stale(self.root))
        write(self.root)
        self.assertFalse((self.root / ".bcr/addons/widget").exists())
        self.assertEqual(stale(self.root), [])

    def test_consumers_are_the_modules_that_override_an_add_on_module(self) -> None:
        generate("widget", root=self.root)
        (self.root / ".bazelignore").write_text("addons\ntests\n")
        (self.root / "tests").mkdir()
        (self.root / "tests/MODULE.bazel").write_text(
            'local_path_override(module_name = "autoload_widget", '
            'path = "../addons/widget")\n'
        )
        write(self.root)
        self.assertIn(
            '["widget"] = List("tests")', (self.root / "addons/consumers.pkl").read_text()
        )
