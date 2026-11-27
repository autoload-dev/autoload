"""addon-module-examples-define-edit-and-pack: every module's examples define edit and pack."""

import unittest

from tools.conventions.rules.addon_module_examples_define_edit_and_pack import (
    AddonModuleExamplesDefineEditAndPack,
)
from tools.conventions.test_support import AddonModuleTest


class AddonModuleExamplesDefineEditAndPackTest(AddonModuleTest):
    rule = AddonModuleExamplesDefineEditAndPack()

    def test_a_module_without_an_example_project_is_reported(self) -> None:
        self.module("widget")
        for name in list(self.files):
            if name.startswith("examples/addons/widget/"):
                self.files.discard(name)
        self.assertEqual(
            ["needs an example project in examples/addons/widget"],
            self.messages(),
        )

    def test_example_projects_define_their_targets(self) -> None:
        self.module("widget")
        build = "examples/addons/widget/BUILD.bazel"
        self.write(
            build, (self.root / build).read_text().replace('name = "edit"', 'name = "e"')
        )
        self.assertEqual(["example project must define :edit"], self.messages())

    def test_example_project_targets_are_read_from_calls_not_text(self) -> None:
        self.module("widget")
        build = "examples/addons/widget/BUILD.bazel"
        text = (self.root / build).read_text()
        # A comment that names the target declares none.
        self.write(
            build, text.replace('name = "edit"', 'name = "e"') + '# name = "edit"\n'
        )
        self.assertEqual(["example project must define :edit"], self.messages())
        # A target's name may follow its other arguments.
        self.write(
            build,
            text.replace(
                'godot_editor(\n    name = "edit",',
                'godot_editor(\n    tags = [],\n    name = "edit",',
            ),
        )
        self.assertEqual([], self.messages())

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
        self.assertEqual([], self.messages())


if __name__ == "__main__":
    unittest.main()
