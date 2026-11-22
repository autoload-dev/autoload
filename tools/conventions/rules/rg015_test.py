"""Add-on modules share the template's layout, and backends live in native/backends."""

import unittest

from tools.addons.new import generate
from tools.conventions.rules.rg015 import AddonModuleLayout
from tools.conventions.test_support import RepositoryTest


class AddonModuleLayoutTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write(".bazelversion", "9.3.0\n")

    def module(self, directory: str, addon: str | None = None) -> None:
        """A module as the generator writes it, in the workspace inventory."""
        for path in generate(directory, addon, root=self.root):
            self.files.add(path.relative_to(self.root).as_posix())

    def evaluate(self) -> list[str]:
        return [item.message for item in AddonModuleLayout().evaluate(self.context())]

    def test_generated_modules_follow_the_layout(self) -> None:
        self.module("widget")
        self.module("firebase", "core")
        self.module("firebase", "analytics")
        self.assertEqual([], self.evaluate())

    def test_missing_files_names_and_shared_settings(self) -> None:
        self.module("widget")
        self.files.discard(".bcr/addons/widget/presubmit.yml")
        source = ".bcr/addons/widget/source.template.json"
        self.write(source, (self.root / source).read_text().replace("widget", "gadget"))
        self.write("addons/widget/MODULE.bazel", 'module(name = "widget")\n')
        self.write("addons/widget/.bazelrc", "common --config=x\n")
        self.assertEqual(
            sorted(self.evaluate()),
            [
                "add-on module must be named autoload_widget",
                "add-on module must own .bcr/addons/widget/presubmit.yml",
                "must import the shared settings: import %workspace%/../module.bazelrc",
                "must release the archive autoload_widget-{VERSION}",
            ],
        )

    def test_registry_templates_of_a_removed_module(self) -> None:
        self.write(".bcr/addons/gone/source.template.json", "{}\n")
        self.assertEqual(["no add-on module owns .bcr/addons/gone"], self.evaluate())

    def test_addon_pkl_amends_the_schema_with_known_values(self) -> None:
        self.module("widget")
        amends = 'amends "../../tools/addons/Addon.pkl"\n'
        for text, message in (
            (
                amends + 'lanes = List("desktop")\nhosts = List("macos")\n',
                "lanes names some",
            ),
            (amends + 'lanes = List("host")\nhosts = List()\n', "hosts names some"),
            (amends + 'hosts = List("macos")\n', "sets lanes"),
            (
                amends + 'lanes = List("host")\nplatforms = List("ios")\n',
                "sets no platforms",
            ),
            ('lanes = List("host")\n', "starts with amends"),
            (
                amends + 'lanes = List("host")\nhosts = "macos"\n',
                "hosts is a List(...) on one line",
            ),
            (
                amends
                + 'lanes = List("host")\ntestOperations = List(\n  "gdunit_test"\n)\n',
                "testOperations is a List(...) on one line",
            ),
        ):
            with self.subTest(text=text):
                self.write("addons/widget/addon.pkl", text)
                findings = self.evaluate()
                self.assertEqual(len(findings), 1)
                self.assertIn(message, findings[0])

    def test_example_projects_define_the_targets_the_lanes_build(self) -> None:
        self.module("widget")
        build = "addons/widget/examples/projects/demo/BUILD.bazel"
        self.write(
            build, (self.root / build).read_text().replace('name = "edit"', 'name = "e"')
        )
        self.assertEqual(["example project must define :edit"], self.evaluate())

    def test_a_module_without_application_lanes_needs_no_app_or_maven_graph(self) -> None:
        self.module("widget")
        self.write(
            "addons/widget/addon.pkl",
            'amends "../../tools/addons/Addon.pkl"\nlanes = List("host")\n',
        )
        build = "addons/widget/examples/projects/demo/BUILD.bazel"
        self.write(
            build, (self.root / build).read_text().replace('name = "app"', 'name = "a"')
        )
        for relative in ("examples/BUILD.bazel", "examples/maven_install.json"):
            self.files.discard(f"addons/widget/{relative}")
        self.assertEqual([], self.evaluate())

    def test_extension_names_are_unique_across_modules(self) -> None:
        self.module("widget")
        self.module("gadget")
        build = "addons/gadget/gadget/BUILD.bazel"
        self.write(
            build,
            (self.root / build)
            .read_text()
            .replace("gadget_extension", "widget_extension"),
        )
        findings = self.evaluate()
        self.assertEqual(len(findings), 1)
        self.assertIn("widget_extension is taken by", findings[0])

    def test_backends_outside_native_are_reported_once_per_directory(self) -> None:
        self.write("examples/addons/widget/backends/apple/BUILD.bazel", "")
        self.write("examples/addons/widget/backends/apple/apple_backend.mm", "")
        self.write("examples/addons/widget/native/backends/linux/BUILD.bazel", "")
        self.assertEqual(
            [
                (
                    "an add-on's backends belong in its native/backends/: "
                    "examples/addons/widget/backends"
                )
            ],
            self.evaluate(),
        )


if __name__ == "__main__":
    unittest.main()
