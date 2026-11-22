"""Staging of an Icon Composer .icon and the actool call that compiles it for macOS."""

import contextlib
import json
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from tools.platforms import compile_icon


class CompileIconTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "icon.json").write_text('{"groups": []}')
        (self.root / "dot.png").write_bytes(b"png bytes")
        self.files = self.root / "files.json"
        self.files.write_text(
            json.dumps(
                {
                    "icon.json": str(self.root / "icon.json"),
                    "Assets/layers/dot.png": str(self.root / "dot.png"),
                }
            )
        )
        self.calls: list[list[str]] = []
        self.staged: dict[str, bytes] = {}
        self.bundle = ""

    def _actool(
        self, returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> Callable[..., subprocess.CompletedProcess]:
        def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
            self.calls.append(command)
            # The staged bundle lives only for the call.
            icon = Path(command[2])
            self.staged = {
                path.relative_to(icon).as_posix(): path.read_bytes()
                for path in icon.rglob("*")
                if path.is_file()
            }
            self.bundle = icon.name
            return subprocess.CompletedProcess(command, returncode, stdout, stderr)

        return run

    def _main(
        self, output: str, actool: Callable[..., subprocess.CompletedProcess]
    ) -> None:
        argv = [
            "compile_icon",
            "--files",
            str(self.files),
            "--name",
            "game",
            "--output",
            output,
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(compile_icon.subprocess, "run", side_effect=actool),
        ):
            compile_icon.main()

    def test_files_are_staged_as_a_named_icon_bundle(self) -> None:
        self._main(str(self.root / "resources"), self._actool())
        self.assertEqual("game.icon", self.bundle)
        self.assertEqual(
            {
                "icon.json": b'{"groups": []}',
                "Assets/layers/dot.png": b"png bytes",
            },
            self.staged,
        )

    def test_actool_compiles_into_the_absolute_output_for_macos(self) -> None:
        with contextlib.chdir(self.root):
            self._main("out/resources", self._actool())
        output = self.root.resolve() / "out/resources"
        self.assertTrue(output.is_dir())
        [command] = self.calls
        self.assertEqual(["xcrun", "actool"], command[:2])
        self.assertEqual("game.icon", Path(command[2]).name)
        self.assertEqual("--compile", command[3])
        self.assertTrue(Path(command[4]).is_absolute())
        self.assertEqual(output, Path(command[4]).resolve())
        for option, value in {
            "--app-icon": "game",
            "--platform": "macosx",
            "--minimum-deployment-target": "26",
        }.items():
            with self.subTest(option=option):
                self.assertEqual(value, command[command.index(option) + 1])

    def test_actool_failure_exits_with_its_output(self) -> None:
        actool = self._actool(1, "actool output\n", "actool error\n")
        with self.assertRaises(SystemExit) as raised:
            self._main(str(self.root / "resources"), actool)
        self.assertEqual("actool output\nactool error\n", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
