"""Tests of the desktop launcher with a stand-in application executable."""

import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import launch_desktop
from launch_common import parse_options

_APP = """#!/bin/sh
printf '%s\\n' "$@" > "$RECORD"
printf '%s\\n' "$HOME" >> "$RECORD"
printf '%s\\n' "$GREETING" >> "$RECORD"
exit 7
"""


class DesktopLaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.app = self.directory / "app"
        self.app.write_text(_APP)
        self.app.chmod(self.app.stat().st_mode | stat.S_IXUSR)
        self.record = self.directory / "record"
        patcher = mock.patch.dict(os.environ, {"RECORD": str(self.record)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def launch(self, *argv: str) -> int:
        manifest = {"platform": "desktop", "executable": "app"}
        return launch_desktop.launch(
            manifest,
            parse_options(argv, "desktop", launch_desktop.OPTIONS),
            lambda path: str(self.directory / path),
        )

    def test_arguments_environment_and_exit_code_pass_through(self) -> None:
        code = self.launch("--headless", "--env", "GREETING=hi", "--", "--verbose")
        self.assertEqual(code, 7)
        self.assertEqual(
            self.record.read_text().splitlines(),
            ["--headless", "--verbose", os.environ["HOME"], "hi"],
        )

    def test_fresh_gives_an_empty_home_and_removes_it(self) -> None:
        self.launch("--fresh")
        home = self.record.read_text().splitlines()[-2]
        self.assertNotEqual(home, os.environ["HOME"])
        self.assertIn("rules_godot_fresh_", home)
        self.assertFalse(Path(home).exists())


if __name__ == "__main__":
    unittest.main()
