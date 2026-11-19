"""An application signed in adhoc mode verifies with codesign, and its archive holds it."""

import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


class AdhocSigningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        paths = [Path(arg) for arg in sys.argv[1:]]
        (cls.bundle,) = [path for path in paths if path.suffix == ".app"]
        (cls.archive,) = [path for path in paths if path.suffix == ".zip"]

    def test_signed_bundle_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            # Tree runfiles contain sandbox symlinks; codesign verifies materialized code.
            materialized = Path(directory) / "Game.app"
            shutil.copytree(self.bundle.resolve(), materialized)
            subprocess.run(
                [
                    "/usr/bin/codesign",
                    "--verify",
                    "--deep",
                    "--strict",
                    str(materialized),
                ],
                check=True,
            )

    def test_archive_holds_the_signed_bundle(self) -> None:
        with zipfile.ZipFile(self.archive) as package:
            self.assertIn("Game.app/Contents/MacOS/Game", package.namelist())


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
