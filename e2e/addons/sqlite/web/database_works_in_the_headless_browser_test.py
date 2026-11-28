"""The SQLite add-on's side module loads in the headless browser and queries a database."""

import subprocess
import sys
import unittest

from python.runfiles import runfiles

LAUNCHER = ""


class SqliteWebTest(unittest.TestCase):
    def test_database_answers_in_the_page(self) -> None:
        launcher = runfiles.Create().Rlocation(LAUNCHER)
        result = subprocess.run(
            [launcher, "--headless", "--port=0"],
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertIn("GDExtension support", output)
        self.assertIn("sqlite on the web: ok", output)


if __name__ == "__main__":
    LAUNCHER = sys.argv.pop(1)
    unittest.main()
