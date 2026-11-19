"""Debug symbol ZIPs of native code and .dSYMs."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.platforms import package_symbols
from tools.platforms.native_fixtures import elf, macho


class PackageSymbolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.runtime = self.root / "runtime"
        self.runtime.write_text("#!/bin/sh\nprintf '%s\\n' runtime-ok\n")

    def test_debug_symbols_zip_holds_native_code_and_dsyms(self) -> None:
        library = self.root / "libgame.so"
        library.write_bytes(elf(b"\x01\x02"))
        dsym = self.root / "Game.dSYM"
        dwarf = dsym / "Contents/Resources/DWARF/Game"
        dwarf.parent.mkdir(parents=True)
        dwarf.write_bytes(macho(bytes(16)))
        output = self.root / "symbols.zip"
        entries = [
            {"destination": "arm64-v8a/libgame.so", "source": str(library)},
            # A launcher script carries no symbols.
            {"destination": "Game", "source": str(self.runtime)},
            {"destination": "Contents/MacOS/Game.dSYM", "source": str(dsym)},
        ]
        package_symbols.package(output, entries)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(
                archive.namelist(),
                [
                    "Contents/MacOS/Game.dSYM/Contents/Resources/DWARF/Game",
                    "arm64-v8a/libgame.so",
                ],
            )
            self.assertEqual(archive.read("arm64-v8a/libgame.so"), library.read_bytes())
        first = output.read_bytes()
        package_symbols.package(output, entries)
        self.assertEqual(output.read_bytes(), first)
        with self.assertRaisesRegex(ValueError, "duplicate symbol path"):
            package_symbols.package(output, entries + entries[:1])
        with self.assertRaisesRegex(ValueError, "relative POSIX"):
            package_symbols.package(
                output, [{"destination": "../libgame.so", "source": str(library)}]
            )


if __name__ == "__main__":
    unittest.main()
