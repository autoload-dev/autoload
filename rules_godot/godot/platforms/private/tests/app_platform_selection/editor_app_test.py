"""In the editor variant the application runs its project from sources with the editor."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


class EditorAppTest(unittest.TestCase):
    def test_application_runs_its_project_from_sources(self) -> None:
        # configured_outputs lists the launcher among the application's files.
        launcher = next(Path(path) for path in sys.argv[1:] if path.endswith(".run"))
        result = subprocess.run(
            [str(launcher), "--headless", "--env", "RUN_LABEL=editor", "--", "--verbose"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertIn("rules_godot unified application passed", output)
        # The build's custom feature, and the tags of an editor running the project.
        self.assertIn(
            "rules_godot features: development=true editor_runtime=true template=false",
            output,
        )
        # Printed only with --verbose, which reached Godot.
        self.assertIn("Loading resource: res://main/main.tscn", output)
        # Nothing was exported: no pack among the run's files.
        runfiles = Path(os.environ["TEST_SRCDIR"])
        self.assertEqual([], [path.name for path in runfiles.rglob("*.pck")])


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
