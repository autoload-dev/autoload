"""
A script fails where the extension it uses has no library, unless ClassDB guards the use.

It fails as well where the extension has no library in the tool configuration of the
validation's execution platform, and the failure names that extension.

An add-on's editor part runs in the editor, which loads the extension everywhere.
"""

import json
import sys
import unittest
from pathlib import Path

FILES = [Path(path) for path in sys.argv[1:]]
sys.argv = sys.argv[:1]


def verdicts() -> dict[str, dict]:
    """The verdict of each validated unit, by unit name."""
    return {
        path.name.removesuffix(".validation.json"): json.loads(path.read_text())
        for path in FILES
        if path.name.endswith(".validation.json")
    }


class AbsentExtensionValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.found = verdicts()

    def test_direct_use_fails_and_names_the_extension(self) -> None:
        verdict = self.found["platform_probe_absent_direct"]
        self.assertTrue(
            any(
                failure.startswith("res://platform_probe/absent/direct.gd:5:")
                and 'Identifier "PlatformProbe" not declared' in failure
                for failure in verdict["failures"]
            ),
            verdict["failures"],
        )
        self.assertIn("res://platform_probe/absent/probe.gdextension", verdict["hint"])

    def test_use_without_a_tool_library_fails_and_names_the_extension(self) -> None:
        verdict = self.found["platform_probe_toolless_direct"]
        self.assertTrue(
            any(
                'Identifier "PlatformProbe" not declared' in failure
                for failure in verdict["failures"]
            ),
            verdict["failures"],
        )
        self.assertIn("res://platform_probe/toolless/probe.gdextension", verdict["hint"])
        self.assertIn("execution platform", verdict["hint"])

    def test_guarded_use_passes(self) -> None:
        self.assertEqual(self.found["platform_probe_absent_guarded"]["failures"], [])

    def test_editor_part_loads_the_extension(self) -> None:
        self.assertEqual(self.found["platform_probe_editor.editor"]["failures"], [])

    def test_direct_use_passes_where_the_platform_has_the_library(self) -> None:
        verdict = self.found["platform_probe_everywhere_direct"]
        self.assertEqual(verdict["failures"], [])
        self.assertNotIn("hint", verdict)


if __name__ == "__main__":
    unittest.main()
