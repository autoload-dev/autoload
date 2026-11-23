"""Complete add-on project layouts do not require empty category packages."""

import unittest

from tools.conventions.rules.rg010 import AddonProjects
from tools.conventions.test_support import RepositoryTest


class AddonProjectsTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write_consumer_modules()

    def evaluate(self, names: tuple[str, ...]) -> list[str]:
        for name in names:
            self.write(name, "")
        context = self.context()
        return [item.message for item in AddonProjects().evaluate(context)]

    def layout(self, root: str) -> tuple[str, ...]:
        return tuple(
            root + "/" + suffix
            for suffix in (
                "BUILD.bazel",
                "demo/BUILD.bazel",
                "demo/project.godot",
                "tests/BUILD.bazel",
                "tests/project.godot",
            )
        )

    def test_demo_and_tests_are_separate_without_empty_category_requirements(
        self,
    ) -> None:
        self.assertEqual(
            [], self.evaluate(self.layout("rules_godot/examples/addons/widget"))
        )

    def test_nested_configuration_cannot_replace_the_test_project(self) -> None:
        root = "rules_godot/examples/addons/widget"
        names = tuple(
            name for name in self.layout(root) if name != root + "/tests/project.godot"
        )
        findings = self.evaluate((*names, root + "/demo/tests/project.godot"))
        self.assertEqual(len(findings), 2)
        self.assertTrue(
            any("must own a separate project" in message for message in findings)
        )
        self.assertTrue(any("reuse those contexts" in message for message in findings))

    def test_each_scope_owns_a_build_file_and_legacy_project_is_not_a_demo(self) -> None:
        root = "rules_godot/examples/addons/widget"
        names = tuple(
            name for name in self.layout(root) if name != root + "/demo/BUILD.bazel"
        )
        findings = self.evaluate((*names, root + "/project/project.godot"))
        self.assertEqual(len(findings), 2)
        self.assertTrue(any("must own a BUILD file" in message for message in findings))

    def test_all_addons_are_discovered_in_both_areas_without_opt_in(self) -> None:
        names = (
            *self.layout("rules_godot/examples/addons/widget"),
            *self.layout("rules_godot/tests/shared_addon"),
            "rules_godot/tests/support/cc_extensions/c_abi/native.cc",
        )
        self.assertEqual([], self.evaluate(names))

    def test_the_shared_addon_scenario_needs_demo_and_test_projects(self) -> None:
        findings = self.evaluate(("rules_godot/tests/shared_addon/BUILD.bazel",))
        self.assertTrue(
            any(
                "rules_godot/tests/shared_addon/demo/project.godot" in item
                for item in findings
            )
        )
        self.assertTrue(
            any(
                "rules_godot/tests/shared_addon/tests/project.godot" in item
                for item in findings
            )
        )


if __name__ == "__main__":
    unittest.main()
