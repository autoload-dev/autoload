"""The launcher finds its modules beside its path in runfiles, wherever its file lives."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SOURCES = (
    Path(os.environ["TEST_SRCDIR"])
    / os.environ["TEST_WORKSPACE"]
    / "tools/platforms/launch"
)


class LaunchEntryTest(unittest.TestCase):
    def test_modules_resolve_from_the_runfiles_directory(self) -> None:
        # As a sandbox may stage it: the entry point's symlink target has no siblings.
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        target, runfiles = directory / "target", directory / "runfiles"
        target.mkdir()
        runfiles.mkdir()
        shutil.copy(_SOURCES / "launch.py", target / "launch.py")
        for module in _SOURCES.glob("launch_*.py"):
            shutil.copy(module, runfiles / module.name)
        (runfiles / "launch.py").symlink_to(target / "launch.py")
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps({"platform": "desktop", "executable": "app"}))
        result = subprocess.run(
            [
                sys.executable,
                str(runfiles / "launch.py"),
                str(manifest),
                str(runfiles),
                "--device=x",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        # The desktop module loaded and rejected the option, so no import failed.
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("--device does not apply to desktop applications", result.stderr)


if __name__ == "__main__":
    unittest.main()
