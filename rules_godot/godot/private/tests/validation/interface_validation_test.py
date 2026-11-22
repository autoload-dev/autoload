"""Dependents validate against a unit's interface as they would against its sources (#158)."""

import json
import sys
import unittest
from pathlib import Path

FILES = [Path(path) for path in sys.argv[1:]]
sys.argv = sys.argv[:1]

_MISUSES = "res://interface/users/misuses.gd"


def verdicts() -> dict[str, dict]:
    """The verdict of each validated unit, by unit name."""
    return {
        path.name.removesuffix(".validation.json"): json.loads(path.read_text())
        for path in FILES
        if path.name.endswith(".validation.json")
    }


class InterfaceValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.found = verdicts()

    def test_declared_uses_pass(self) -> None:
        # Inferred member types, coroutines, enums, inner classes, a lambda member, a
        # static constructor and preloaded scene, texture and sound, from a script and a
        # scene.
        self.assertEqual([], self.found["interface_user"]["failures"])

    def test_misuses_fail_as_against_the_sources(self) -> None:
        failures = "\n".join(self.found["interface_misuser"]["failures"])
        for line, message in [
            (6, 'Function "settle()" is a coroutine, so it must be called with "await".'),
            (7, 'Cannot assign a value of type Vector2 to variable "at"'),
            (8, 'Cannot assign a value of type int to variable "width"'),
            (9, 'Cannot assign a value of type AudioStreamWAV to variable "beep"'),
            (10, 'Cannot assign a value of type float to variable "step"'),
        ]:
            self.assertIn(f"{_MISUSES}:{line}: Parse Error: {message}", failures)

    def test_a_body_error_fails_only_its_own_unit(self) -> None:
        self.assertIn(
            "res://interface/base/body_error.gd:7:",
            "\n".join(self.found["interface_base"]["failures"]),
        )
        self.assertEqual([], self.found["interface_body_error_user"]["failures"])


if __name__ == "__main__":
    unittest.main()
