"""
no-fixtures-in-public-documentation regressions for which documentation must avoid
regression fixtures.
"""

import unittest

from tools.conventions.rules.no_fixtures_in_public_documentation import FixtureReferences
from tools.conventions.test_support import RepositoryTest


class FixtureReferencesTest(RepositoryTest):
    def test_addon_fixture_references_are_checked_but_layout_schemas_are_not_fixtures(
        self,
    ) -> None:
        self.write(
            "docs/public/layout.md",
            "tests/projects/<name>/\ntests/addons/<name>/\nUse //tests/addons/counter:demo\n",
        )
        context = self.context()
        findings = list(FixtureReferences().evaluate(context))
        self.assertEqual([item.location.line for item in findings], [3])

    def test_scenario_paths_are_fixtures_but_scenario_layouts_are_not(self) -> None:
        self.write(
            "docs/public/layout.md",
            "tests/smoke/<operating_system>/ and tests/script_run/\n"
            "Copy tests/smoke/linux/main.gd\n"
            "See godot/private/tests/fixtures/README.md\n",
        )
        findings = list(FixtureReferences().evaluate(self.context()))
        self.assertEqual([item.location.line for item in findings], [2])

    def test_fixture_reference_fails_only_in_user_documentation(self) -> None:
        public = (
            "README.md",
            "examples/demo/README.md",
            "docs/public/usage.md",
            "docs/public/development.md",
        )
        other = (
            "docs/internal/development.md",
            "rules_godot/docs/internal/godot-pipeline/README.md",
            "docs/AGENTS.md",
            "tests/notes.md",
        )
        for name in (*public, *other):
            self.write(name, "Intro.\nRun //tests/projects/demo:app.\n")
        context = self.context()
        findings = list(FixtureReferences().evaluate(context))
        self.assertEqual(
            sorted((name, 2) for name in public),
            sorted((item.location.path, item.location.line) for item in findings),
        )


if __name__ == "__main__":
    unittest.main()
