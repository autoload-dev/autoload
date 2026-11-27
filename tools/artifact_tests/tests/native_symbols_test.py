"""The inspection helper's own reader of ELF build IDs and Mach-O UUIDs."""

import struct
import unittest

from tools.artifact_tests.native_symbols import elf_build_id, elf_sections, macho_uuids
from tools.artifact_tests.tests.native_fixtures import elf, macho, universal

_ARM64 = bytes.fromhex("5ef81f68a5cb3b0c82ffe288702e954d")
_X86_64 = bytes.fromhex("9ed63934491e3c349862618a9c738b79")


def _thin(count: int, command_bytes: int, commands: bytes) -> bytes:
    """A 64-bit Mach-O header announcing count load commands of command_bytes."""
    header = struct.pack("<IiiIIIII", 0xFEEDFACF, 0, 0, 6, count, command_bytes, 0, 0)
    return header + commands


class NativeSymbolsTest(unittest.TestCase):
    def test_uuids_identify_each_cpu(self) -> None:
        self.assertEqual([_ARM64.hex()], macho_uuids(macho(_ARM64)))
        self.assertEqual(
            [_ARM64.hex(), _X86_64.hex()],
            macho_uuids(universal(macho(_ARM64), macho(_X86_64, cpu="x86_64"))),
        )
        self.assertEqual([], macho_uuids(macho()))

    def test_truncated_macho_files_are_rejected(self) -> None:
        command = struct.pack("<II", 0x1B, 24) + _ARM64
        # A load command without the UUID, so that the reader goes on to the next.
        other = struct.pack("<II", 0x32, 24) + bytes(16)
        cases = {
            "not a little-endian Mach-O file": b"\x7fELF",
            "Truncated universal header": bytes.fromhex("cafebabe"),
            "Truncated universal CPU table": struct.pack(">II", 0xCAFEBABE, 2),
            "Truncated or overlapping universal slice": struct.pack(
                ">IIIIIII", 0xCAFEBABE, 1, 0x0100000C, 0, 28, 64, 0
            ),
            "Truncated Mach-O header": bytes.fromhex("cffaedfe"),
            "Truncated Mach-O load commands": _thin(1, 24, command[:16]),
            "Truncated Mach-O load command size": _thin(1, 24, command[:4] + bytes(20)),
            "Truncated Mach-O load command": _thin(2, 24, other),
        }
        for message, data in cases.items():
            with self.subTest(message):
                with self.assertRaises(ValueError) as raised:
                    macho_uuids(data)
                self.assertEqual(message, str(raised.exception))

    def test_build_id_identifies_elf(self) -> None:
        sections = elf_sections(elf(bytes.fromhex("7eb76e5a")))
        self.assertEqual("7eb76e5a", elf_build_id(sections))
        self.assertNotIn(".symtab", sections)
        self.assertIsNone(elf_build_id({}))
        with self.assertRaisesRegex(ValueError, "^not an ELF file$"):
            elf_sections(macho())


if __name__ == "__main__":
    unittest.main()
