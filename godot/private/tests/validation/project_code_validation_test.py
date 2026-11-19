"""The content validation runs no project code and types autoloads by their scripts."""

import json
import sys
import unittest
from pathlib import Path

FILES = [Path(path) for path in sys.argv[1:]]
sys.argv = sys.argv[:1]


def verdicts() -> dict[str, dict]:
    """The verdict of each validated unit, by target name."""
    return {
        path.name.removesuffix(".validation.json"): json.loads(path.read_text())
        for path in FILES
        if path.name.endswith(".validation.json")
    }


class ProjectCodeValidationTest(unittest.TestCase):
    # Fixture code that runs fails its validation (fixtures/guard/guard.gd), so a verdict
    # exists only for a validation that ran none.
    def test_units_whose_code_would_run_pass(self) -> None:
        found = verdicts()
        for unit in ["guard", "autoloads", "autoload_user", "code", "preloader"]:
            with self.subTest(unit=unit):
                self.assertEqual([], found[unit]["failures"])

    def test_a_wrong_argument_to_an_autoload_fails(self) -> None:
        failures = verdicts()["autoload_misuse"]["failures"]
        for path, call in [
            (
                "res://autoload_users/wrong_script_call.gd:5",
                'Invalid argument for "track()"',
            ),
            (
                "res://autoload_users/wrong_scene_call.gd:5",
                'Invalid argument for "show_hud()"',
            ),
        ]:
            with self.subTest(call=call):
                self.assertTrue(
                    any(f.startswith(path) and call in f for f in failures), failures
                )


if __name__ == "__main__":
    unittest.main()
