"""Stripping, build IDs, UUIDs and the CPU and SDK identity of native code."""

import os
import struct
import tempfile
import unittest
from pathlib import Path

from tools.platforms import native_symbols
from tools.platforms.native_fixtures import elf, macho, universal


def _with_command(thin: bytes, body: bytes) -> bytes:
    """Return the thin Mach-O file with body appended as one more load command."""
    count, size = struct.unpack_from("<II", thin, 16)
    header = thin[:16] + struct.pack("<II", count + 1, size + len(body)) + thin[24:32]
    return header + thin[32:] + body


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

    def test_version_min_commands_name_the_sdk(self) -> None:
        # LC_VERSION_MIN_IPHONEOS names the device for arm64 and the Simulator otherwise.
        for command, cpu, sdk in [
            (0x24, "arm64", "macos"),
            (0x25, "arm64", "ios_device"),
            (0x25, "x86_64", "ios_simulator"),
        ]:
            self.assertEqual(
                native_symbols.native_slices(
                    _with_command(macho(cpu=cpu), struct.pack("<4I", command, 16, 0, 0))
                ),
                {cpu: sdk},
            )
        # The last command that names an SDK decides, even when it names an unknown one.
        unknown = struct.pack("<6I", 0x32, 24, 99, 0, 0, 0)
        with self.assertRaisesRegex(ValueError, "Missing or unsupported Mach-O SDK"):
            native_symbols.native_slices(_with_command(macho(sdk="macos"), unknown))
        with self.assertRaisesRegex(ValueError, "Truncated Mach-O build version"):
            native_symbols.native_slices(
                _with_command(macho(), struct.pack("<II", 0x32, 16) + bytes(8))
            )

    def test_malformed_mach_o_files_are_rejected(self) -> None:
        thin = macho(sdk="macos")
        for data, message in [
            (thin[:16] + struct.pack("<II", 1, 64) + thin[24:], "load commands$"),
            (thin[:16] + struct.pack("<II", 2, 24) + thin[24:], "load command$"),
            (thin[:36] + struct.pack("<I", 4) + thin[40:], "load command size"),
            (
                thin[:16] + struct.pack("<II", 1, 32) + thin[24:] + bytes(8),
                "declared size",
            ),
            (struct.pack(">II", 0xCAFEBABE, 2) + bytes(16), "universal CPU table"),
            (
                struct.pack(">IIIIII", 0xCAFEBABE, 1, 0x0100000C, 0, 8, len(thin))
                + bytes(4)
                + thin,
                "overlapping universal slice",
            ),
            (b"\xcf\xfa\xed\xfe" + bytes(4) + thin[8:], "Mach-O CPU type 0"),
            (b"\x7fELF" + bytes([3, 1]) + bytes(32), "Unsupported ELF encoding"),
            (b"\x7fELF" + bytes([2, 1, 1]) + bytes(32), "Unsupported ELF machine 0"),
            (b"\xce\xfa\xed\xfe" + bytes(32), "Unsupported native binary format"),
        ]:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValueError, message),
            ):
                native_symbols.native_slices(data)
        with self.assertRaisesRegex(ValueError, "Duplicate CPU slice"):
            native_symbols.native_slices(universal(thin, thin))


if __name__ == "__main__":
    unittest.main()
