"""A macOS application's .dSYM carries the DWARF of its extension library."""

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.platforms.native_symbols import macho_uuids

LIBRARY = "Contents/Resources/native/bin/macos.arm64.release/libdsym_extension.so"


class DsymTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        paths = [Path(arg) for arg in sys.argv[1:]]
        # The application's launcher lies beside its bundle.
        (cls.bundle,) = [
            path.with_suffix(".app") for path in paths if path.suffix == ".run"
        ]
        (symbols,) = [path for path in paths if path.name.endswith("_debug_symbols.zip")]
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        with zipfile.ZipFile(symbols) as archive:
            dwarf = [
                name
                for name in archive.namelist()
                if name.startswith(LIBRARY + ".dSYM/Contents/Resources/DWARF/")
            ]
            if len(dwarf) != 1:
                raise AssertionError(f"Expected one DWARF file, found {dwarf}")
            cls.dwarf = Path(archive.extract(dwarf[0], directory.name))

    def test_compile_units_name_the_sources(self) -> None:
        info = subprocess.run(
            ["/usr/bin/xcrun", "dwarfdump", "--debug-info", str(self.dwarf)],
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout
        self.assertIn("DW_TAG_compile_unit", info)
        self.assertIn("dsym_extension.cc", info)
        self.assertIn("dsym_fixture_init", info)
        self.assertIn("DW_AT_decl_line", info)

    def test_uuid_matches_packaged_library(self) -> None:
        library = self.bundle / LIBRARY
        self.assertEqual(
            macho_uuids(library.read_bytes()), macho_uuids(self.dwarf.read_bytes())
        )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
