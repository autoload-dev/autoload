"""The dSYM of a release iOS application matches its executable."""

import argparse
import sys
import tempfile
import unittest
from pathlib import Path

from godot.platforms.private.tests.library_composition.ios_apps import unpacked
from tools.platforms.native_symbols import macho_uuids


class IosDebugSymbolsTest(unittest.TestCase):
    def test_dsym_has_the_executables_uuids(self) -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--app", nargs="+", required=True)
        parser.add_argument("--dsym", nargs="+", required=True, type=Path)
        args = parser.parse_args(sys.argv[1:])
        # rules_apple names the dSYM's DWARF file after the executable.
        dwarf = [path for path in args.dsym if path.parent.name == "DWARF"]
        self.assertTrue(dwarf, "a dSYM; it needs --apple_generate_dsym")
        with tempfile.TemporaryDirectory() as directory:
            _, _, executable = unpacked(args.app, Path(directory))
            uuids = macho_uuids(executable.read_bytes())
        self.assertTrue(uuids)
        for path in dwarf:
            self.assertEqual(macho_uuids(path.read_bytes()), uuids, path)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
