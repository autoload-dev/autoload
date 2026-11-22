"""Nested Bazel must not pass its Python launcher's import policy to build tools."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.tool_environment import nested_tool_environment, start_build_tool


class ToolEnvironmentTest(unittest.TestCase):
    def test_actual_sibling_import_under_polluted_launcher_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "configure.py"
            script.write_text("import module_graph\nprint(module_graph.VALUE)\n")
            (root / "module_graph.py").write_text("VALUE = 'declared-sibling'\n")
            polluted = dict(os.environ, PYTHONSAFEPATH="1", RULES_GODOT_KEEP="preserved")
            failing = subprocess.run(
                [sys.executable, str(script)],
                env=polluted,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(failing.returncode, 0)
            self.assertIn("No module named 'module_graph'", failing.stderr)
            isolated = nested_tool_environment(polluted)
            passing = subprocess.run(
                [sys.executable, str(script)],
                env=isolated,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(passing.stdout.strip(), "declared-sibling")
            self.assertEqual(polluted["PYTHONSAFEPATH"], "1")
            self.assertEqual(isolated["RULES_GODOT_KEEP"], "preserved")
            self.assertEqual(set(polluted) - set(isolated), {"PYTHONSAFEPATH"})

    def test_build_tool_starts_in_invocation_directory_and_nested_environment(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            polluted = {
                "BUILD_WORKING_DIRECTORY": directory,
                "PYTHONSAFEPATH": "1",
                "RULES_GODOT_KEEP": "preserved",
            }
            previous = Path.cwd()
            try:
                with patch.dict(os.environ, polluted, clear=True):
                    start_build_tool()
                    self.assertEqual(Path(directory).resolve(), Path.cwd().resolve())
                    self.assertNotIn("PYTHONSAFEPATH", os.environ)
                    self.assertEqual("preserved", os.environ["RULES_GODOT_KEEP"])
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
