"""A parse error fails exactly its unit's validation, and no import, initialization or export."""

import json
import sys
import unittest
from pathlib import Path

FILES = [Path(path) for path in sys.argv[1:]]
sys.argv = sys.argv[:1]


def built(name: str) -> Path:
    """The one built file or directory named name."""
    found = [path for path in FILES if path.name == name]
    if len(found) != 1:
        raise AssertionError(f"{name}: expected one built file, found {found}")
    return found[0]


class ParseErrorValidationTest(unittest.TestCase):
    def test_only_the_broken_unit_fails(self) -> None:
        verdicts = {
            path.name.removesuffix(".validation.json"): json.loads(path.read_text())
            for path in FILES
            if path.name.endswith(".validation.json")
        }
        broken = verdicts.pop("parse_error_script")
        self.assertEqual(
            1, len([f for f in broken["failures"] if "Parse Error" in f]), broken
        )
        self.assertTrue(
            broken["failures"][0].startswith(
                "res://script_errors/parse_error.gd:4: Parse Error"
            ),
            broken,
        )
        self.assertIn("abstract_class", verdicts)
        for unit, verdict in verdicts.items():
            with self.subTest(unit=unit):
                self.assertEqual([], verdict["failures"])

    def test_export_and_initialization_succeed(self) -> None:
        self.assertGreater(built("broken_pack.pck").stat().st_size, 0)
        initialized = built("broken_run.view.initialized")
        self.assertTrue((initialized / ".godot/global_script_class_cache.cfg").is_file())


if __name__ == "__main__":
    unittest.main()
