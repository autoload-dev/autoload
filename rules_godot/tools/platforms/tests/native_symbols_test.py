"""Stripping, build IDs and UUIDs of native code."""

import os
import struct
import tempfile
import unittest
from pathlib import Path

from tools.platforms import native_symbols
from tools.platforms.native_fixtures import elf, macho


class NativeSymbolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.runtime = self.root / "runtime"
        self.runtime.write_text("#!/bin/sh\nprintf '%s\\n' runtime-ok\n")

    def test_strip_copies_what_is_not_native_code(self) -> None:
        output = self.root / "stripped"
        native_symbols.strip("/nonexistent/strip", [], str(self.runtime), str(output))
        self.assertEqual(output.read_bytes(), self.runtime.read_bytes())
        self.assertTrue(os.access(output, os.X_OK))

    def test_build_ids_and_uuids_identify_native_code(self) -> None:
        sections = native_symbols.elf_sections(elf(bytes.fromhex("7eb76e5a")))
        self.assertEqual(native_symbols.elf_build_id(sections), "7eb76e5a")
        self.assertNotIn(".symtab", sections)
        self.assertIsNone(native_symbols.elf_build_id({}))
        arm64 = macho(bytes.fromhex("5ef81f68a5cb3b0c82ffe288702e954d"))
        x86_64 = macho(bytes.fromhex("9ed63934491e3c349862618a9c738b79"))
        self.assertEqual(
            native_symbols.macho_uuids(arm64), ["5ef81f68a5cb3b0c82ffe288702e954d"]
        )
        universal = struct.pack(">II", 0xCAFEBABE, 2)
        universal += struct.pack(">IIIII", 0x01000007, 3, 64, len(x86_64), 0)
        universal += struct.pack(">IIIII", 0x0100000C, 0, 64 + len(x86_64), len(arm64), 0)
        universal = universal.ljust(64, b"\0") + x86_64 + arm64
        self.assertEqual(
            native_symbols.macho_uuids(universal),
            ["9ed63934491e3c349862618a9c738b79", "5ef81f68a5cb3b0c82ffe288702e954d"],
        )
        path = self.root / "universal"
        path.write_bytes(universal)
        self.assertEqual(native_symbols.native_format(path), "macho")
        self.assertIsNone(native_symbols.native_format(self.runtime))


if __name__ == "__main__":
    unittest.main()
