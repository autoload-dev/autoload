"""Run the setup action's Node tests of its Bazel shutdown."""

import subprocess
import sys
import unittest
from pathlib import Path

NODE = Path(sys.argv.pop(1)).resolve()
TESTS = Path(".github/actions/setup/stop-bazel/post.test.js")


class SetupActionTest(unittest.TestCase):
    def test_stop_bazel_passes_its_node_tests(self) -> None:
        self.assertTrue(TESTS.is_file(), "no setup action in the test's runfiles")
        result = subprocess.run(
            [NODE, "--test", TESTS],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
