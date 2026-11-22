"""Boot the application with a registered patched source-built runtime and read its probe."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


class PatchedRuntimeTest(unittest.TestCase):
    def test_runtime_has_the_custom_module_and_patch(self) -> None:
        bundle = Path(os.environ["TEST_SRCDIR"]) / sys.argv[1]
        result = subprocess.run(
            [str(bundle / "Contents/MacOS/app"), "--headless"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("rules_godot: BazelProbe answer 42", result.stdout)
        self.assertIn(
            "rules_godot: engine name Godot Engine with Bazel patch", result.stdout
        )
        self.assertIn("rules_godot: source-built engine custom module OK", result.stdout)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
