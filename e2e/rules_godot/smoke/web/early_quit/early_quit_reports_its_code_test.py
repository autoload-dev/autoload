"""A web application that quits in its first frames reports its own exit code."""

import os
import subprocess
import sys
import unittest

from python.runfiles import runfiles

LAUNCHER = ""

# (code, frames): frames 0 quits in _ready.
_CASES = [(0, 0), (3, 0), (42, 2), (5, 2)]


def _run(launcher: str, code: int, frames: int) -> tuple[int | None, str, str]:
    """Run the application; a run that hangs ends with SIGTERM, so the launcher ends its browser."""
    # Port 0: any free port, so parallel tests do not wait for each other's.
    process = subprocess.Popen(
        [
            launcher,
            "--headless",
            "--port=0",
            "--",
            "--",
            f"code={code}",
            f"frames={frames}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(os.environ),
    )
    try:
        stdout, stderr = process.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        process.terminate()
        stdout, stderr = process.communicate()
        return None, stdout, stderr + "\nthe application hung"
    return process.returncode, stdout, stderr


class EarlyQuitTest(unittest.TestCase):
    def test_each_quit_reports_its_code(self) -> None:
        files = runfiles.Create()
        launcher = files.Rlocation(LAUNCHER) if files else None
        if launcher is None:
            self.fail("the test runs with `bazel test`, which supplies the launcher")
        for code, frames in _CASES:
            with self.subTest(code=code, frames=frames):
                returncode, stdout, stderr = _run(launcher, code, frames)
                self.assertEqual(code, returncode, stdout + stderr)
                self.assertIn(f"early quit after {frames} frames with {code}", stdout)


if __name__ == "__main__":
    LAUNCHER = sys.argv.pop(1)
    unittest.main()
