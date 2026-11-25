"""Regressions for project targets named like their directory."""

import unittest

from tools.conventions.context import Call, Location
from tools.conventions.rules.rg019 import ProjectTargetNames
from tools.conventions.test_support import RepositoryTest


def project(path: str, name: str) -> Call:
    return Call(Location(path, 1), "godot_project", frozenset({"name"}), name)


class ProjectTargetNamesTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write("MODULE.bazel", "")
        self.write("examples/addons/sqlite/project.godot", "")
        self.write("examples/addons/sqlite/BUILD.bazel", "")

    def findings(self, *calls: Call) -> list[str]:
        context = self.context(calls=calls)
        return [item.message for item in ProjectTargetNames().evaluate(context)]

    def test_a_project_named_like_its_directory_passes(self) -> None:
        self.assertEqual(
            self.findings(project("examples/addons/sqlite/BUILD.bazel", "sqlite")), []
        )

    def test_a_project_named_otherwise_is_reported(self) -> None:
        self.assertEqual(
            self.findings(project("examples/addons/sqlite/BUILD.bazel", "demo")),
            ["name the project of examples/addons/sqlite like its directory: sqlite"],
        )

    def test_further_projects_beside_the_named_one_pass(self) -> None:
        self.assertEqual(
            self.findings(
                project("examples/addons/sqlite/BUILD.bazel", "sqlite"),
                project("examples/addons/sqlite/BUILD.bazel", "test_project"),
            ),
            [],
        )

    def test_projects_of_packages_without_project_file_pass(self) -> None:
        self.write("e2e/rules_godot/smoke/BUILD.bazel", "")
        self.assertEqual(
            self.findings(project("e2e/rules_godot/smoke/BUILD.bazel", "variant")), []
        )


if __name__ == "__main__":
    unittest.main()
