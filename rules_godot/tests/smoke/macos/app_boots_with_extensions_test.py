"""Inspect and boot the macOS smoke application."""

import os
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path


class MacosApplicationTest(unittest.TestCase):
    def test_archive_holds_the_pack_and_the_application_boots(self) -> None:
        runfiles = Path(os.environ["TEST_SRCDIR"])
        bundle = runfiles / sys.argv[1]
        archive = runfiles / sys.argv[2]
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
        self.assertTrue(any(name.endswith(".pck") for name in names), names)
        self.assertTrue(any(name.endswith("/app") for name in names), names)
        result = subprocess.run(
            [bundle / "Contents/MacOS/app", "--headless"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn(
            "rules_godot smoke: C ABI and godot-cpp extensions loaded, imported texture usable",
            output,
        )


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
