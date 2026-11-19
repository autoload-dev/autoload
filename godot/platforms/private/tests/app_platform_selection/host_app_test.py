"""The exported host application runs the main scene of its start pack."""

import subprocess
import sys
import unittest
from pathlib import Path


class HostAppTest(unittest.TestCase):
    def test_application_loads_its_start_pack(self) -> None:
        bundle = Path(sys.argv[1])
        executable = bundle / (
            "Contents/MacOS/app" if sys.platform == "darwin" else "app"
        )
        result = subprocess.run(
            [str(executable), "--headless"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("rules_godot unified application passed", result.stdout)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
