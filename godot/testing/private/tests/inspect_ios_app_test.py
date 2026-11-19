"""The iOS inspector's symbol, file, Info.plist and dSYM checks over synthetic bundles."""

import contextlib
import io
import plistlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from godot.testing.private import inspect_ios_app
from tools.platforms.native_fixtures import macho, universal

_ARM64 = bytes.fromhex("5ef81f68a5cb3b0c82ffe288702e954d")
_X86_64 = bytes.fromhex("9ed63934491e3c349862618a9c738b79")
# nm -U output: defined symbols, a local one among them, with C's leading underscore.
_NM = """0000000100003f50 T _godot_entry
0000000100003f60 t _local_helper
0000000100003f70 T plain_name

"""


class InspectIosAppTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.nm_calls: list[list[str]] = []

    def _app(self, executable: bytes = b"") -> Path:
        """An .app directory with an executable, a resource and an Info.plist."""
        app = self.root / "game.app"
        (app / "Frameworks").mkdir(parents=True, exist_ok=True)
        (app / "game").write_bytes(executable or macho(_ARM64))
        (app / "Frameworks/extension.framework").write_bytes(b"framework")
        (app / "Info.plist").write_bytes(
            plistlib.dumps(
                {"CFBundleExecutable": "game", "UIRequiredDeviceCapabilities": []}
            )
        )
        return app

    def _ipa(self, app: Path) -> Path:
        """The .ipa of an .app directory, with the bundle under Payload/."""
        ipa = self.root / "game.ipa"
        with zipfile.ZipFile(ipa, "w") as archive:
            for member in sorted(app.rglob("*")):
                if member.is_file():
                    name = f"Payload/{app.name}/{member.relative_to(app).as_posix()}"
                    archive.write(member, name)
        return ipa

    def _dwarf(self, executable: bytes) -> Path:
        """A dSYM's DWARF file, as rules_apple names it after the executable."""
        dwarf = self.root / "game.app.dSYM/Contents/Resources/DWARF/game"
        dwarf.parent.mkdir(parents=True, exist_ok=True)
        dwarf.write_bytes(executable)
        return dwarf

    def _nm(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        self.nm_calls.append(command)
        return subprocess.CompletedProcess(command, 0, _NM, "")

    def _inspect(self, app: Path, *options: str) -> str:
        """Run the inspector's command line; return what it prints."""
        stdout = io.StringIO()
        with (
            mock.patch.object(
                sys, "argv", ["inspect_ios_app", "--app", str(app), *options]
            ),
            mock.patch.object(inspect_ios_app.subprocess, "run", side_effect=self._nm),
            contextlib.redirect_stdout(stdout),
        ):
            inspect_ios_app.main()
        return stdout.getvalue()

    def assertLacks(self, message: str, app: Path, *options: str) -> None:
        with self.assertRaises(ValueError) as raised:
            self._inspect(app, *options)
        self.assertEqual("The application lacks: " + message, str(raised.exception))

    def test_symbols_need_a_leading_underscore_definition(self) -> None:
        app = self._app()
        self._inspect(app, "--symbol", "godot_entry", "--symbol", "local_helper")
        [command] = self.nm_calls
        self.assertEqual(["/usr/bin/nm", "-U"], command[:2])
        self.assertEqual("game", Path(command[2]).name)
        self.assertLacks("symbol plain_name", app, "--symbol", "plain_name")
        self.assertLacks("symbol _godot_entry", app, "--symbol", "_godot_entry")

    def test_missing_files_and_infoplist_keys_are_reported(self) -> None:
        app = self._app()
        self._inspect(
            app,
            "--file",
            "Frameworks/extension.framework",
            "--infoplist-key",
            "UIRequiredDeviceCapabilities",
        )
        self.assertLacks(
            "file Frameworks/missing.framework",
            app,
            "--file",
            "Frameworks/missing.framework",
        )
        self.assertLacks(
            "Info.plist key NSCameraUsageDescription",
            app,
            "--infoplist-key",
            "NSCameraUsageDescription",
        )

    def test_all_missing_parts_are_reported_together(self) -> None:
        app = self._app()
        for source in (app, self._ipa(app)):
            with self.subTest(source=source.name):
                self.assertLacks(
                    "symbol missing_entry, file missing.txt, Info.plist key NSMissing",
                    source,
                    "--symbol",
                    "missing_entry",
                    "--file",
                    "missing.txt",
                    "--infoplist-key",
                    "NSMissing",
                )
                self.assertEqual(
                    "rules_godot: iOS application verified\n",
                    self._inspect(source, "--symbol", "godot_entry", "--file", "game"),
                )

    def test_required_dsym_must_be_present(self) -> None:
        app = self._app()
        missing = "a dSYM; build it with --apple_generate_dsym"
        self.assertLacks(missing, app, "--dsym-required")
        plist = self.root / "game.app.dSYM/Contents/Info.plist"
        plist.parent.mkdir(parents=True)
        plist.write_bytes(b"plist")
        self.assertLacks(missing, app, "--dsym-required", "--dsym", str(plist))
        dwarf = self._dwarf(macho(_ARM64))
        self._inspect(app, "--dsym-required", "--dsym", str(plist), "--dsym", str(dwarf))
        # Without --dsym-required, no dSYM is looked for.
        self._inspect(app)

    def test_dsym_must_carry_the_executables_uuids(self) -> None:
        mismatch = "a dSYM with the executable's UUID"
        thin = self._app(macho(_ARM64))
        self.assertLacks(
            mismatch, thin, "--dsym-required", "--dsym", str(self._dwarf(macho(_X86_64)))
        )
        both = universal(macho(_ARM64), macho(_X86_64, cpu="x86_64"))
        fat = self._app(both)
        self._inspect(fat, "--dsym-required", "--dsym", str(self._dwarf(both)))
        self.assertLacks(
            mismatch, fat, "--dsym-required", "--dsym", str(self._dwarf(macho(_ARM64)))
        )


if __name__ == "__main__":
    unittest.main()
