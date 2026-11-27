"""
no-end-to-end-tests-in-public-documentation regressions for which documentation must avoid
the repository's end-to-end tests.
"""

import unittest

from tools.conventions.rules.no_end_to_end_tests_in_public_documentation import (
    EndToEndTestReferences,
)
from tools.conventions.test_support import RepositoryTest


class EndToEndTestReferencesTest(RepositoryTest):
    def test_scenarios_and_addon_tests_are_reported_but_layout_schemas_are_not(
        self,
    ) -> None:
        self.write(
            "docs/public/layout.md",
            "e2e/addons/<module>/ and e2e/rules_godot/<scenario>/ in e2e/rules_godot/\n"
            "Copy e2e/rules_godot/smoke/linux/main.gd\n"
            "bazel test //e2e/addons/sqlite/database\n"
            "See godot/private/e2e/fixtures/README.md and examples/addons/sqlite\n",
        )
        findings = list(EndToEndTestReferences().evaluate(self.context()))
        self.assertEqual([item.location.line for item in findings], [2, 3])

    def test_reference_fails_only_in_user_documentation(self) -> None:
        public = (
            "README.md",
            "addons/sqlite/README.md",
            "examples/demo/README.md",
            "docs/public/usage.md",
            "rules_godot/docs/public/usage.md",
        )
        other = (
            "docs/internal/development.md",
            "rules_godot/docs/internal/godot-pipeline/README.md",
            "addons/AGENTS.md",
            "e2e/notes.md",
        )
        for name in (*public, *other):
            self.write(name, "Intro.\nRun //e2e/addons/demo:edit.\n")
        findings = list(EndToEndTestReferences().evaluate(self.context()))
        self.assertEqual(
            sorted((name, 2) for name in public),
            sorted((item.location.path, item.location.line) for item in findings),
        )


if __name__ == "__main__":
    unittest.main()
