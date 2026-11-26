"""Boot the application with build profiles of classes and of build options and read its classes."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


def run(bundle: str) -> str:
    """Return the output of a headless run of an application bundle; fail on a nonzero exit."""
    # A bundle's executable is named after its application.
    executable = next(
        (Path(os.environ["TEST_SRCDIR"]) / bundle / "Contents/MacOS").iterdir()
    )
    result = subprocess.run(
        [str(executable), "--headless"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


class BuildProfileTest(unittest.TestCase):
    def test_the_profile_leaves_its_classes_out_of_the_runtime(self) -> None:
        full = run(sys.argv[1])
        self.assertIn("rules_godot: Tree registered true", full)
        self.assertIn("rules_godot: CodeEdit registered true", full)
        without_tree = run(sys.argv[2])
        self.assertIn("rules_godot: Tree registered false", without_tree)
        self.assertIn("rules_godot: CodeEdit registered true", without_tree)
        self.assertIn("rules_godot: source-built engine custom module OK", without_tree)

    def test_a_runtime_profile_compiles_its_build_options(self) -> None:
        # disable_advanced_gui leaves Tree and CodeEdit out of the runtime variant.
        variant = run(sys.argv[3])
        self.assertIn("rules_godot: Tree registered false", variant)
        self.assertIn("rules_godot: CodeEdit registered false", variant)
        self.assertIn("rules_godot: source-built engine custom module OK", variant)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
