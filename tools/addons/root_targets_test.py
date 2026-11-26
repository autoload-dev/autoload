"""
root.targets names the add-on modules that addons.bzl lists, as `aspect generate` writes it.

The root ignores addons/, so the test compares the two generated files: the setup checks
reject an addons.bzl that misses a module, and this test a root.targets that misses one,
which would leave the module's tests and lint out of every development verb. The test's
arguments are the two files.
"""

import re
import sys
import unittest
from pathlib import Path

from tools.addons import declarations

REPOSITORIES = Path(sys.argv.pop(1))
TARGETS = Path(sys.argv.pop(1))


class RootTargetsTest(unittest.TestCase):
    def test_the_root_targets_are_those_of_the_repositories(self) -> None:
        names = re.findall(r'"@(\w+)"', REPOSITORIES.read_text())
        self.assertTrue(names)
        expected = declarations.targets([(name, "") for name in names])
        self.assertEqual(
            expected, TARGETS.read_text(), "root.targets is stale; run `aspect generate`"
        )


if __name__ == "__main__":
    unittest.main()
