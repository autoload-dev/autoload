"""Type errors, failing base scripts and undeclared global classes fail their units' validations."""

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


class ScriptErrorValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.found = verdicts()

    def assert_fails(self, unit: str, script: str, line: int, message: str) -> None:
        """Assert that the unit fails with Godot's message at the line and to load script."""
        failures = self.found[unit]["failures"]
        self.assertTrue(
            any(f.startswith(f"{script}:{line}:") and message in f for f in failures),
            failures,
        )
        self.assertIn(f'{script}: Failed to load script "{script}"', "\n".join(failures))

    def test_type_error_fails_its_unit(self) -> None:
        self.assert_fails(
            "type_error_script",
            "res://script_errors/type_error.gd",
            3,
            'Cannot assign a value of type "String" as "int".',
        )

    def test_failing_base_fails_its_unit_and_the_extending_one(self) -> None:
        self.assert_fails(
            "parse_error_script",
            "res://script_errors/parse_error.gd",
            4,
            "Parse Error",
        )
        self.assert_fails(
            "failing_base_script",
            "res://script_errors/dependent.gd",
            1,
            'Could not resolve super class inheritance from "res://script_errors/parse_error.gd".',
        )

    def test_global_class_resolves_only_through_deps(self) -> None:
        self.assert_fails(
            "undeclared_class_user",
            "res://shape_users/undeclared.gd",
            4,
            'Could not find type "ValidatedShape" in the current scope.',
        )
        for unit in ["shape", "declared_class_user"]:
            with self.subTest(unit=unit):
                self.assertEqual([], self.found[unit]["failures"])


if __name__ == "__main__":
    unittest.main()
