"""
The content validation follows the project's debug/gdscript/warnings settings.

The first argument names the project whose validations the other arguments are; each
project's test has its own runfiles, since the validations of the same units in different
contexts share their short paths.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT = sys.argv[1]
FILES = [Path(path) for path in sys.argv[2:]]
sys.argv = sys.argv[:1]

# Whether each unit's untyped declaration fails it, by project: Godot's default
# directory_rules exempt res://addons from warnings unless the project's include the
# add-on's directory.
_FAILS = {
    "project": {"untyped": False, "checked.runtime": False},
    "warnings_project": {"untyped": True, "checked.runtime": False},
    "addon_warnings_project": {"untyped": True, "checked.runtime": True},
}
_SCRIPTS = {
    "untyped": "res://warnings/untyped.gd:3",
    "checked.runtime": "res://addons/checked/untyped.gd:3",
}
_WARNING = 'Variable "value" has no static type. (Warning treated as error.)'


def verdicts() -> dict[str, dict]:
    """The verdict of each validated unit, by unit name."""
    return {
        path.name.removesuffix(".validation.json"): json.loads(path.read_text())
        for path in FILES
        if path.name.endswith(".validation.json")
    }


class WarningValidationTest(unittest.TestCase):
    def test_raised_warnings_fail_where_they_apply(self) -> None:
        found = verdicts()
        for unit, fails in _FAILS[PROJECT].items():
            with self.subTest(unit=unit):
                failures = found[unit]["failures"]
                self.assertEqual(
                    fails,
                    any(f.startswith(_SCRIPTS[unit]) and _WARNING in f for f in failures),
                    failures,
                )
                if not fails:
                    self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
