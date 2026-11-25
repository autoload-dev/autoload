"""A release tag finds its module, its release test and whether the registry gets it."""

import tempfile
import unittest
from pathlib import Path

from tools.ci.release_module import describe


def module(name: str) -> str:
    return f'module(name = "{name}", version = "0.1.0")\n'


class ReleaseModuleTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "rules_godot").mkdir()
        (self.root / "rules_godot/MODULE.bazel").write_text(
            module("autoload_rules_godot")
        )
        (self.root / ".bcr/rules_godot").mkdir(parents=True)
        (self.root / ".bcr/rules_godot/metadata.template.json").write_text("{}")
        for directory, name in (
            ("widget", "autoload_widget"),
            ("gadget", "autoload_gadget"),
        ):
            (self.root / "addons" / directory).mkdir(parents=True)
            (self.root / "addons" / directory / "MODULE.bazel").write_text(module(name))
        (self.root / ".bcr/addons/widget").mkdir(parents=True)
        (self.root / ".bcr/addons/widget/metadata.template.json").write_text("{}")

    def test_the_ruleset_releases_from_its_directory_with_its_registry_test_module(
        self,
    ) -> None:
        self.assertEqual(
            describe("autoload_rules_godot-v0.2.0", self.root),
            {
                "name": "autoload_rules_godot",
                "version": "0.2.0",
                "root": "rules_godot",
                "bcr": "true",
                "test": "python3 -m tools.ci.release_archive rules_godot",
            },
        )

    def test_an_add_on_module_is_found_by_the_name_its_module_declares(self) -> None:
        widget = describe("autoload_widget-v1.0.0-rc.1", self.root)
        self.assertEqual(widget["root"], "addons/widget")
        self.assertEqual(widget["version"], "1.0.0-rc.1")
        self.assertEqual(widget["bcr"], "true")
        self.assertEqual(
            widget["test"], "python3 -m tools.ci.release_archive addons/widget"
        )
        self.assertEqual(describe("autoload_gadget-v0.1.0", self.root)["bcr"], "false")

    def test_unknown_modules_and_malformed_tags_are_refused(self) -> None:
        for tag in ("autoload_other-v0.1.0", "v0.1.1", "autoload_widget-0.1.0"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                describe(tag, self.root)


if __name__ == "__main__":
    unittest.main()
