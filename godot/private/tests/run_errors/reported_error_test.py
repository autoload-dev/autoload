"""A test fails when Godot reports an error while the game runs, though Godot exits with 0."""

import subprocess
import sys
import unittest


class ReportedErrorTest(unittest.TestCase):
    def test_reported_error_fails_the_test(self) -> None:
        result = subprocess.run(
            [sys.argv[1]], capture_output=True, text=True, check=False
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            "Godot reported 1 error(s) while the game ran, first at "
            "res://main/main.gd:5: rules_godot run test error",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
