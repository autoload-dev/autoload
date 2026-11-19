"""Copy isolation, entitlement scope and failure propagation of local signing."""

import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.platforms import sign_macos


class SigningTest(unittest.TestCase):
    def test_readonly_input_stays_unchanged_and_entitlements_only_reach_app(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "unsigned.app"
            source.mkdir()
            binary = source / "library.dylib"
            binary.write_bytes(b"\xcf\xfa\xed\xfeoriginal")
            binary.chmod(0o444)
            source.chmod(0o555)
            output = root / "signed.app"
            calls = []

            def invoke(command: list[str], **_kwargs: object) -> None:
                calls.append(command)
                if "--target_to_sign" in command:
                    target = Path(command[command.index("--target_to_sign") + 1])
                    self.assertTrue(target.stat().st_mode & stat.S_IWUSR)
                    self.assertTrue(target.parent.stat().st_mode & stat.S_IWUSR)

            argv = [
                "sign_macos",
                "--input",
                str(source),
                "--output",
                str(output),
                "--archive",
                str(root / "signed.zip"),
                "--codesigning-tool",
                "tool",
                "--identity",
                "-",
                "--entitlements",
                "app.entitlements",
            ]
            try:
                with (
                    mock.patch.object(sys, "argv", argv),
                    mock.patch.object(sign_macos.subprocess, "run", side_effect=invoke),
                ):
                    sign_macos.main()
                signed = [call for call in calls if "--target_to_sign" in call]
                self.assertEqual(len(signed), 2)
                self.assertNotIn("--entitlements", signed[0])
                self.assertIn("--entitlements", signed[1])
                self.assertEqual(binary.read_bytes(), b"\xcf\xfa\xed\xfeoriginal")
                self.assertFalse(binary.stat().st_mode & stat.S_IWUSR)
                self.assertFalse(source.stat().st_mode & stat.S_IWUSR)
                self.assertTrue((root / "signed.zip").exists())
            finally:
                source.chmod(0o755)
                binary.chmod(0o644)

    def test_partial_failure_does_not_publish_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "unsigned.app"
            source.mkdir()
            (source / "library.dylib").write_bytes(b"\xcf\xfa\xed\xfeoriginal")
            archive = root / "signed.zip"
            argv = [
                "sign_macos",
                "--input",
                str(source),
                "--output",
                str(root / "signed.app"),
                "--archive",
                str(archive),
                "--codesigning-tool",
                "tool",
                "--identity",
                "-",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    sign_macos.subprocess,
                    "run",
                    side_effect=RuntimeError("signing failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "signing failed"),
            ):
                sign_macos.main()
            self.assertFalse(archive.exists())
            self.assertTrue((source / "library.dylib").exists())


if __name__ == "__main__":
    unittest.main()
