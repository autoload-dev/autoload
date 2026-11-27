"""Add-on modules share the template's layout, and backends live in native/backends."""

import sys
import unittest
from pathlib import Path

from tools.addons.modules import ROOT
from tools.addons.new import generate
from tools.conventions.context import Buildozer, Context
from tools.conventions.rules.addon_module_layout import AddonModuleLayout
from tools.conventions.test_support import RepositoryTest

BUILDOZER = Path(sys.argv.pop(1)).resolve()


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

    def findings(self) -> list[tuple[str, str]]:
        """The rule's findings, with the calls of the BUILD files as buildozer reads them."""
        workspace = self.workspace()
        context = Context(
            workspace, Buildozer(self.root, BUILDOZER), self.context().bazel
        )
        return [
            (item.status, item.message) for item in AddonModuleLayout().evaluate(context)
        ]

    def evaluate(self) -> list[str]:
        return [message for _, message in self.findings()]

    def test_generated_modules_follow_the_layout(self) -> None:
        self.module("widget")
        self.module("firebase", "core")
        self.module("firebase", "analytics")
        self.assertEqual([], self.evaluate())

    def test_missing_files_and_names(self) -> None:
        self.module("widget")
        self.files.discard(".bcr/addons/widget/presubmit.yml")
        self.files.discard("addons/widget/REPO.bazel")
        self.write("addons/widget/MODULE.bazel", 'module(name = "widget")\n')
        self.assertEqual(
            sorted(self.evaluate()),
            [
                "add-on module must be named autoload_widget",
                "add-on module must own .bcr/addons/widget/presubmit.yml",
                "add-on module must own addons/widget/REPO.bazel",
            ],
        )

    def test_the_module_root_holds_its_files_add_ons_and_referenced_packages(
        self,
    ) -> None:
        self.module("widget")
        self.write("addons/widget/third_party/BUILD.bazel", "")
        self.write("addons/widget/tests/x/BUILD.bazel", "")
        # Packages that another package of the module or another module loads by label.
        self.write("addons/widget/shared/BUILD.bazel", 'filegroup(name = "files")\n')
        self.write("addons/widget/widget/defs.bzl", 'SHARED = "//shared:files"\n')
        self.write("addons/widget/rules/defs.bzl", "")
        self.write("addons/widget/rules/BUILD.bazel", "")
        self.write(
            "examples/addons/widget/rules.bzl",
            'load("@autoload_widget//rules:defs.bzl", "x")\n',
        )
        # A package that only names itself, and one that no label names.
        self.write("addons/widget/stray/BUILD.bazel", 'alias(actual = "//stray:x")\n')
        self.write("addons/widget/lonely/BUILD.bazel", "")
        # A directory that is no package, though a label names a package below it.
        self.write("addons/widget/misc/tools/BUILD.bazel", "")
        self.write("addons/widget/widget/tools.bzl", 'TOOLS = "//misc/tools:t"\n')
        self.write("addons/widget/notes.txt", "")
        root = "the module's root holds only its files, its add-ons, bcr/, tests/, third_party/"
        referenced = "and packages that other packages load by label"
        self.assertEqual(
            sorted(m for m in self.evaluate() if m.startswith("addons/widget/")),
            [
                f"addons/widget/lonely: {root} {referenced}",
                f"addons/widget/misc: {root} {referenced}",
                f"addons/widget/notes.txt: {root} {referenced}",
                f"addons/widget/stray: {root} {referenced}",
            ],
        )

    def test_registry_templates_of_a_removed_module(self) -> None:
        self.write(".bcr/addons/gone/source.template.json", "{}\n")
        self.assertEqual(["no add-on module owns .bcr/addons/gone"], self.evaluate())

    def test_a_regular_dependency_is_not_loaded_by_tests_alone(self) -> None:
        self.module("widget")
        manifest = (self.root / "addons/widget/MODULE.bazel").read_text()
        self.write(
            "addons/widget/MODULE.bazel",
            manifest + 'bazel_dep(name = "rules_testing", version = "0.9.0")\n',
        )
        self.write(
            "addons/widget/tests/BUILD.bazel",
            'load("@rules_testing//lib:analysis_test.bzl", "analysis_test")\n',
        )
        self.assertEqual(
            [
                (
                    "only tests load rules_testing, which every consumer inherits: "
                    "test with it from e2e/addons/widget/"
                )
            ],
            self.evaluate(),
        )
        self.write(
            "addons/widget/widget/defs.bzl", 'load("@rules_testing//lib:util.bzl", "x")\n'
        )
        self.assertEqual([], self.evaluate())

    def test_example_projects_define_their_targets(self) -> None:
        self.module("widget")
        build = "examples/addons/widget/BUILD.bazel"
        self.write(
            build, (self.root / build).read_text().replace('name = "edit"', 'name = "e"')
        )
        self.assertEqual(["example project must define :edit"], self.evaluate())

    def test_example_project_targets_are_read_from_calls_not_text(self) -> None:
        self.module("widget")
        build = "examples/addons/widget/BUILD.bazel"
        text = (self.root / build).read_text()
        # A comment that names the target declares none.
        self.write(
            build, text.replace('name = "edit"', 'name = "e"') + '# name = "edit"\n'
        )
        self.assertEqual(["example project must define :edit"], self.evaluate())
        # A target's name may follow its other arguments.
        self.write(
            build,
            text.replace(
                'godot_editor(\n    name = "edit",',
                'godot_editor(\n    tags = [],\n    name = "edit",',
            ),
        )
        self.assertEqual([], self.evaluate())

    def test_a_computed_example_target_name_is_not_checked(self) -> None:
        self.module("widget")
        build = "examples/addons/widget/BUILD.bazel"
        text = (self.root / build).read_text()
        self.write(build, text.replace('name = "edit"', 'name = "e" + "dit"'))
        self.assertEqual(
            [("not_checked", "cannot read every target name of examples/addons/widget")],
            self.findings(),
        )

    def test_example_projects_need_no_app(self) -> None:
        self.module("widget")
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

    def test_extension_names_are_read_from_calls_not_text(self) -> None:
        self.module("widget")
        self.module("gadget")
        build = "addons/gadget/gadget/BUILD.bazel"
        text = (self.root / build).read_text()
        # A comment declares no extension; a name after other arguments still counts.
        self.write(build, text + '# godot_cc_extension(name = "widget_extension")\n')
        self.assertEqual([], self.evaluate())
        moved = text.replace(
            'godot_cc_extension(\n    name = "gadget_extension",',
            'godot_cc_extension(\n    tags = [],\n    name = "widget_extension",',
        )
        self.assertNotEqual(moved, text)
        self.write(build, moved)
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
