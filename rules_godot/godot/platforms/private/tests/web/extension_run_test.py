"""
A web application with an extension starts in the headless browser, loads the extension's
side module and exits with its own code.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path


def _launch_command() -> list[str]:
    """The command bazel run runs: the launcher over the application's manifest, in the runfiles."""
    runfiles = Path(os.environ["TEST_SRCDIR"])
    (manifest,) = runfiles.glob("_main/**/app.run.launch.json")
    entry = runfiles / "_main/tools/platforms/launch/launch.py"
    return ["python3", str(entry), str(manifest), str(runfiles)]


class WebExtensionRunTest(unittest.TestCase):
    def test_extension_loads_in_the_page(self) -> None:
        result = subprocess.run(
            [*_launch_command(), "--headless", "--port=0"],
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(3, result.returncode, output)
        self.assertIn("GDExtension support", output)
        self.assertIn("rules_godot extension initialized", output)
        self.assertIn("res://native/hello.gdextension", output)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
