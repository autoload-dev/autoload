"""shared-module-files regressions: add-on modules keep the files the generator shares."""

import unittest

from tools.addons.modules import ROOT
from tools.addons.new import generate
from tools.conventions.rules.shared_module_files import SharedModuleFiles
from tools.conventions.test_support import RepositoryTest


class SharedModuleFilesTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write(".bazelversion", "9.3.0\n")
        self.write(
            ".bcr/rules_godot/metadata.template.json",
            (ROOT / ".bcr/rules_godot/metadata.template.json").read_text(),
        )
        for path in generate("widget", root=self.root):
            self.files.add(path.relative_to(self.root).as_posix())

    def findings(self) -> list[str]:
        return [
            f"{item.location.path}: {item.message}"
            for item in SharedModuleFiles().evaluate(self.context())
        ]

    def test_generated_modules_keep_their_shared_files(self) -> None:
        self.assertEqual([], self.findings())

    def test_a_changed_shared_file_is_reported_but_not_the_module_s_own(self) -> None:
        self.write("addons/widget/.bazelrc", "common --config=x\n")
        self.write(".bcr/addons/widget/source.template.json", "{}\n")
        self.write("addons/widget/MODULE.bazel", 'module(name = "autoload_widget")\n')
        message = "differs from what the add-on generator writes; run `aspect generate`"
        self.assertEqual(
            [
                f".bcr/addons/widget/source.template.json: {message}",
                f"addons/widget/.bazelrc: {message}",
            ],
            self.findings(),
        )

    def test_files_named_alike_outside_add_on_modules_are_not_shared(self) -> None:
        self.write("addons/notes/.bazelrc", "common --config=x\n")
        self.write("rules_godot/.bazelrc", "common --config=x\n")
        self.assertEqual([], self.findings())


if __name__ == "__main__":
    unittest.main()
