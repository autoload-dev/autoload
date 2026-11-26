"""
The lint check's gate (check.sh), which the aspect `python` of check.bzl runs for each
linted target: it fails with the reports of the linters that found something.
The test's argument is the gate.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECK = Path(sys.argv.pop(1)).resolve()


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stamp = self.root / "target.lint"

    def report(self, name: str, exit_code: int, text: str) -> list[str]:
        """A linter's exit code and report, as the gate's arguments."""
        (self.root / f"{name}.out").write_text(text)
        (self.root / f"{name}.out.exit_code").write_text(f"{exit_code}\n")
        return [str(self.root / f"{name}.out.exit_code"), str(self.root / f"{name}.out")]

    def check(self, *reports: list[str]) -> subprocess.CompletedProcess[str]:
        arguments = [argument for report in reports for argument in report]
        return subprocess.run(
            [CHECK, self.stamp, *arguments], capture_output=True, text=True, check=False
        )

    def test_passes_and_writes_its_stamp_when_every_linter_passes(self) -> None:
        result = self.check(self.report("ruff", 0, ""), self.report("ty", 0, "ok\n"))
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertTrue(self.stamp.exists())

    def test_fails_with_the_report_of_each_linter_that_found_something(self) -> None:
        result = self.check(
            self.report("ruff", 1, "F401 `os` imported but unused\n"),
            self.report("ty", 0, "All checks passed\n"),
            self.report("other", 2, "invalid-return-type\n"),
        )
        self.assertEqual(1, result.returncode)
        self.assertEqual(
            "F401 `os` imported but unused\ninvalid-return-type\n", result.stdout
        )
        self.assertFalse(self.stamp.exists())

    def test_passes_without_reports(self) -> None:
        self.assertEqual(0, self.check().returncode)


if __name__ == "__main__":
    unittest.main()
