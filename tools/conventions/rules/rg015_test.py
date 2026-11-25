"""Add-on modules share the template's layout, and backends live in native/backends."""

import unittest

from tools.addons.modules import ROOT
from tools.addons.new import generate
from tools.conventions.rules.rg015 import AddonModuleLayout
from tools.conventions.test_support import RepositoryTest


class AddonModuleLayoutTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write(".bazelversion", "9.3.0\n")
        self.write(
            ".bcr/rules_godot/metadata.template.json",
            (ROOT / ".bcr/rules_godot/metadata.template.json").read_text(),
        )

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
        for template in ("source", "metadata"):
            path = f".bcr/addons/widget/{template}.template.json"
            self.write(path, (self.root / path).read_text().replace("widget", "gadget"))
        self.write("addons/widget/MODULE.bazel", 'module(name = "widget")\n')
        self.write("addons/widget/.bazelrc", "common --config=x\n")
        self.assertEqual(
            sorted(self.evaluate()),
            [
                "add-on module must be named autoload_widget",
                "add-on module must own .bcr/addons/widget/presubmit.yml",
                "must be .bcr/rules_godot/metadata.template.json with the module's homepage",
                "must import the shared settings: import %workspace%/../module.bazelrc",
                "must release the archive autoload_widget-{VERSION}",
            ],
        )

    def test_the_module_root_holds_its_files_add_ons_and_declared_packages(self) -> None:
        self.module("widget")
        self.write("addons/widget/third_party/BUILD.bazel", "")
        self.write("addons/widget/tests/x/BUILD.bazel", "")
        self.write("addons/widget/shared/BUILD.bazel", "")
        self.write("addons/widget/stray/BUILD.bazel", 'filegroup(name = "files")\n')
        self.write("addons/widget/notes.txt", "")
        pkl = (self.root / "addons/widget/addon.pkl").read_text()
        self.write("addons/widget/addon.pkl", pkl + 'sharedPackages = List("shared")\n')
        root = "the module's root holds only its files, its add-ons, third_party/, tests/, bcr/"
        self.assertEqual(
            sorted(m for m in self.evaluate() if m.startswith("addons/widget/")),
            [
                f"addons/widget/notes.txt: {root} and the sharedPackages of addon.pkl",
                f"addons/widget/stray: {root} and the sharedPackages of addon.pkl",
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
                amends + 'lanes = List("host")\ndesktops = List("macos")\n',
                "lanes names some",
            ),
            (
                amends + 'lanes = List("desktop")\ndesktops = List()\n',
                "desktops names some",
            ),
            (amends + 'desktops = List("macos")\n', "sets lanes"),
            (
                amends + 'lanes = List("desktop")\nplatforms = List("ios")\n',
                "sets no platforms",
            ),
            ('lanes = List("desktop")\n', "starts with amends"),
            (
                amends + 'lanes = List("desktop")\ndesktops = "macos"\n',
                "desktops is a List(...) on one line",
            ),
            (
                amends
                + 'lanes = List("desktop")\ntestOperations = List(\n  "gdunit_test"\n)\n',
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
        build = "examples/addons/widget/BUILD.bazel"
        self.write(
            build, (self.root / build).read_text().replace('name = "edit"', 'name = "e"')
        )
        self.assertEqual(["example project must define :edit"], self.evaluate())

    def test_an_example_project_keeps_its_tests_in_tests(self) -> None:
        self.module("widget")
        build = "examples/addons/widget/BUILD.bazel"
        text = (self.root / build).read_text()
        self.write(
            build, text + 'godot_test(\n    name = "starts",\n    pack = ":pack",\n)\n'
        )
        self.assertEqual(
            ["example project's tests live in examples/addons/widget/tests/: :starts"],
            self.evaluate(),
        )

    def test_a_module_without_application_lanes_needs_no_app(self) -> None:
        self.module("widget")
        self.write(
            "addons/widget/addon.pkl",
            'amends "../../tools/addons/Addon.pkl"\nlanes = List("desktop")\n',
        )
        build = "examples/addons/widget/BUILD.bazel"
        self.write(
            build, (self.root / build).read_text().replace('name = "app"', 'name = "a"')
        )
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
