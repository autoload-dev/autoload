"""Regressions for Godot projects and tests outside the add-on modules."""

import unittest

from tools.conventions.context import Call, Location
from tools.conventions.rules.rg021 import NoGodotRunsInAddonModules
from tools.conventions.test_support import RepositoryTest


def call(path: str, kind: str) -> Call:
    return Call(Location(path, 1), kind, frozenset({"name"}), "t")


class NoGodotRunsInAddonModulesTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write("addons/widget/MODULE.bazel", "")
        self.write(
            "addons/widget/addon.pkl",
            'amends "../../tools/addons/Addon.pkl"\n'
            'lanes = List("desktop")\n'
            'testOperations = List("widget_test")\n',
        )
        self.write("addons/widget/widget/BUILD.bazel", "")
        self.write("addons/widget/tests/BUILD.bazel", "")

    def findings(self, *calls: Call) -> list[str]:
        context = self.context(calls=calls)
        return [
            item.location.path for item in NoGodotRunsInAddonModules().evaluate(context)
        ]

    def test_unit_tests_and_the_add_ons_pass(self) -> None:
        self.assertEqual(
            self.findings(
                call("addons/widget/widget/BUILD.bazel", "godot_cc_extension"),
                call("addons/widget/tests/BUILD.bazel", "cc_test"),
            ),
            [],
        )

    def test_godot_projects_and_runs_belong_to_the_root_module(self) -> None:
        self.write("addons/widget/tests/fixtures/project.godot", "")
        self.assertEqual(
            self.findings(
                call("addons/widget/tests/BUILD.bazel", "godot_project"),
                call("addons/widget/tests/BUILD.bazel", "godot_test"),
                call("addons/widget/tests/BUILD.bazel", "godot_runtime_profile"),
                call("addons/widget/tests/BUILD.bazel", "widget_test"),
            ),
            [
                "addons/widget/tests/fixtures/project.godot",
                "addons/widget/tests/BUILD.bazel",
                "addons/widget/tests/BUILD.bazel",
                "addons/widget/tests/BUILD.bazel",
                "addons/widget/tests/BUILD.bazel",
            ],
        )

    def test_the_registry_test_modules_and_the_root_module_may_run_godot(self) -> None:
        self.write("addons/widget/bcr/smoke/MODULE.bazel", "")
        self.write("addons/widget/bcr/smoke/project.godot", "")
        self.write("addons/widget/bcr/smoke/BUILD.bazel", "")
        self.write("e2e/addons/widget/project.godot", "")
        self.write("e2e/addons/widget/BUILD.bazel", "")
        self.assertEqual(
            self.findings(
                call("addons/widget/bcr/smoke/BUILD.bazel", "widget_test"),
                call("e2e/addons/widget/BUILD.bazel", "godot_project"),
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
