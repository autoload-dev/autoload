"""Application/add-on type follows location identically in examples and tests."""

import unittest

from tools.conventions.rules.rg009 import ProjectPlaces
from tools.conventions.test_support import RepositoryTest


class ProjectPlacesTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write_consumer_modules()

    def evaluate(self, *names: str) -> list[str]:
        for name in names:
            self.write(name, "")
        context = self.context()
        return [item.message for item in ProjectPlaces().evaluate(context)]

    def test_projects_at_the_fixed_places_of_their_consumers_are_allowed(self) -> None:
        self.assertEqual(
            [],
            self.evaluate(
                "examples/game/BUILD.bazel",
                "examples/game/project.godot",
                "e2e/rules_godot/mobile/BUILD.bazel",
                "e2e/rules_godot/mobile/android/project.godot",
                "addons/widget/MODULE.bazel",
                "examples/addons/widget/BUILD.bazel",
                "examples/addons/widget/project.godot",
                "e2e/addons/widget/suites/BUILD.bazel",
                "e2e/addons/widget/suites/project.godot",
                "e2e/addons/widget/strict/BUILD.bazel",
                "e2e/addons/widget/strict/project.godot",
            ),
        )

    def test_legacy_groups_unit_packages_and_unnamed_roots_are_rejected(self) -> None:
        findings = self.evaluate(
            "examples/project.godot",
            "e2e/rules_godot/project.godot",
            "e2e/rules_godot/smoke/project.godot",
            "e2e/project.godot",
        )
        self.assertEqual(len(findings), 4)
        self.assertTrue(
            all("project at a fixed place of their consumer" in item for item in findings)
        )

    def test_test_inputs_of_a_gazelle_language_are_no_projects(self) -> None:
        self.assertEqual(
            [],
            self.evaluate(
                "tools/gazelle/godot/testdata/tree/game/project.godot",
                "tools/gazelle/godot/testdata/tree/game/BUILD.out",
            ),
        )

    def test_an_add_on_module_holds_no_project(self) -> None:
        findings = self.evaluate(
            "addons/runner/MODULE.bazel",
            "addons/runner/tests/fixtures/suites/project.godot",
            "addons/runner/runner/project.godot",
        )
        self.assertEqual(len(findings), 2)

    def test_an_end_to_end_project_may_hold_fixture_projects(self) -> None:
        findings = self.evaluate(
            "addons/runner/MODULE.bazel",
            "e2e/addons/runner/BUILD.bazel",
            "e2e/addons/runner/fixtures/suites/project.godot",
            "e2e/addons/runner/project.godot",
            "e2e/project.godot",
        )
        self.assertEqual(len(findings), 1)

    def test_a_nested_module_is_not_an_exemption_for_project_placement(self) -> None:
        self.assertEqual(
            len(
                self.evaluate(
                    "consumers/demo/MODULE.bazel",
                    "consumers/demo/android/project.godot",
                )
            ),
            1,
        )

    def test_a_registry_test_module_is_one_project_or_one_per_directory(self) -> None:
        self.assertEqual(
            [],
            self.evaluate(
                "rules_godot/bcr/smoke/MODULE.bazel",
                "rules_godot/bcr/smoke/BUILD.bazel",
                "rules_godot/bcr/smoke/project.godot",
                "addons/widget/MODULE.bazel",
                "addons/widget/bcr/apps/MODULE.bazel",
                "addons/widget/bcr/apps/desktop/BUILD.bazel",
                "addons/widget/bcr/apps/desktop/project.godot",
            ),
        )
        self.assertEqual(
            len(
                self.evaluate(
                    "rules_godot/bcr/deep/MODULE.bazel",
                    "rules_godot/bcr/deep/projects/smoke/project.godot",
                )
            ),
            1,
        )

    def test_the_engines_directory_beside_the_applications_is_no_project(self) -> None:
        self.assertEqual(
            [],
            self.evaluate(
                "examples/engines/simulation/BUILD.bazel",
                "examples/engines/simulation/modules/field/config.py",
                "examples/game/BUILD.bazel",
                "examples/game/project.godot",
            ),
        )

    def test_project_needs_configuration_and_own_build(self) -> None:
        findings = self.evaluate(
            "e2e/rules_godot/raw_library/native.cc",
            "examples/app/project.godot",
        )
        self.assertEqual(len(findings), 3)
        self.assertTrue(
            any("must contain a Godot configuration" in item for item in findings)
        )
        self.assertTrue(any("must own a BUILD file" in item for item in findings))

    def test_extension_fixture_inputs_and_generated_templates_do_not_define_projects(
        self,
    ) -> None:
        self.assertEqual(
            [],
            self.evaluate(
                "tools/c_abi/native.cc",
                "tools/resources/project.godot.tpl",
                "e2e/rules_godot/parser_test.py",
                "godot/private/default_project.godot",
            ),
        )


if __name__ == "__main__":
    unittest.main()
