"""Boot the packaged application with the registered prebuilt runtime."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


class PrebuiltApplicationTest(unittest.TestCase):
    def test_application_boots_the_registered_prebuilt_runtime(self) -> None:
        bundle = Path(os.environ["TEST_SRCDIR"]) / sys.argv[1]
        # The bundle <name>.app or <name>.bundle holds the executable <name>.
        name = bundle.stem
        executable = bundle / (
            f"Contents/MacOS/{name}" if sys.platform == "darwin" else name
        )
        result = subprocess.run(
            [str(executable), "--headless"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            f"rules_godot engine configuration runtime {sys.argv[2]}", result.stdout
        )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
