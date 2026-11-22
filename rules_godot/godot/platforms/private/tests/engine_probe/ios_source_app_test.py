"""
Inspect an iOS Simulator application built with the source-built arm64 Simulator engine:
its executable defines the godot-cpp extension's entry symbol. No simulator runs it.
"""

import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.platforms.apple_bundle import application_bundle

ENTRY = "example_library_init"


class IOSSourceAppTest(unittest.TestCase):
    def test_source_built_app_defines_extension_entry(self) -> None:
        archive = Path(os.environ["TEST_SRCDIR"], sys.argv[1])
        work = Path(tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR")))
        app = application_bundle(archive, work)
        info = plistlib.loads((app / "Info.plist").read_bytes())
        # Defined symbols, local ones included: the exported symbols list that static
        # extension libraries add keeps everything else out of the exports.
        symbols = {
            line.split()[-1]
            for line in subprocess.run(
                ["/usr/bin/nm", "-U", str(app / info["CFBundleExecutable"])],
                stdout=subprocess.PIPE,
                text=True,
                check=True,
            ).stdout.splitlines()
            if line.strip()
        }
        self.assertIn("_" + ENTRY, symbols)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
