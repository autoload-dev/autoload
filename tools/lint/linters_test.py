"""
The linters of `aspect lint` (.aspect/config.axl) are those of the lint check (check.bzl).

The Aspect CLI configures its lint task in AXL, which cannot load the Starlark of the
aspects, so each lists the linters of linters.bzl: `aspect lint` to apply their fixes, the
lint check through the aspects' `requires`. The test's arguments are the two files.
"""

import re
import sys
import unittest
from pathlib import Path

CONFIG = Path(sys.argv.pop(1))
CHECK = Path(sys.argv.pop(1))


class LintersTest(unittest.TestCase):
    def test_aspect_lint_runs_the_linters_of_the_lint_check(self) -> None:
        config = re.findall(r"linters\.bzl%(\w+)", CONFIG.read_text())
        required = re.findall(r"requires = \[([^\]]*)\]", CHECK.read_text())
        check = [name for names in required for name in re.findall(r"\w+", names)]
        self.assertTrue(config)
        self.assertEqual(sorted(check), sorted(config))


if __name__ == "__main__":
    unittest.main()
