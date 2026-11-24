"""Lint the GitHub workflows with jactionlint, shellcheck and pyflakes off as before."""

import subprocess
import sys
import unittest
from pathlib import Path

JACTIONLINT = Path(sys.argv.pop(1)).resolve()


class WorkflowsTest(unittest.TestCase):
    def test_workflows_pass_jactionlint(self) -> None:
        workflows = sorted(str(path) for path in Path(".github/workflows").glob("*.y*ml"))
        self.assertTrue(workflows, "no workflows in the test's runfiles")
        result = subprocess.run(
            # The tests' runfiles are no Git checkout, where jactionlint finds its settings.
            [
                JACTIONLINT,
                "--config-file=.github/jactionlint.yaml",
                "--shellcheck=",
                "--pyflakes=",
                *workflows,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
