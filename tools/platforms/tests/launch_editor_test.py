"""Tests of the editor variant's launcher with a stand-in runner."""

import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import launch_editor
from launch_common import LaunchError, parse_options

_RUNNER = """#!/bin/sh
printf '%s\\n' "$@" > "$RECORD"
"""


class EditorLaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, True)
        runner = self.directory / "runner"
        runner.write_text(_RUNNER)
        runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
        self.record = self.directory / "record"
        patcher = mock.patch.dict(os.environ, {"RECORD": str(self.record)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def launch(self, *argv: str) -> int:
        options = parse_options(list(argv), "editor", launch_editor.OPTIONS)
        return launch_editor.launch(
            {"platform": "editor", "runner": "runner", "manifest": "app.run.json"},
            options,
            lambda path: str(self.directory / path),
        )

    def test_options_reach_the_runner(self) -> None:
        self.assertEqual(
            self.launch("--headless", "--env", "LEVEL=3", "--", "--verbose"), 0
        )
        self.assertEqual(
            self.record.read_text().splitlines(),
            [
                "--env",
                "LEVEL=3",
                "--manifest",
                str(self.directory / "app.run.json"),
                "--headless",
                "--verbose",
            ],
        )

    def test_device_options_and_controlled_godot_options_fail(self) -> None:
        with self.assertRaisesRegex(LaunchError, "--device does not apply to editor"):
            self.launch("--device=x")
        with self.assertRaisesRegex(LaunchError, "--main-pack would replace the project"):
            self.launch("--", "--main-pack", "x.pck")


if __name__ == "__main__":
    unittest.main()
