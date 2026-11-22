"""Each godot_cc_extension shared library exports only its entry symbol."""

import os
import struct
import unittest
from pathlib import Path

from tools.platforms.native_symbols import (
    elf_sections,
    macho_load_commands,
    native_format,
)

FIXTURE = "godot/extension/tests/symbol_isolation"
PROBES = ["Alpha", "Beta"]


def elf_exports(data: bytes) -> set[str]:
    """Return the defined, default-visibility global, weak and GNU unique symbols of a 64-bit ELF file."""
    sections = elf_sections(data)
    table, strings = sections[".dynsym"], bytes(sections[".dynstr"])
    exports = set()
    for offset in range(0, len(table), 24):
        name, info, other, section = struct.unpack_from("<IBBH", table, offset)
        if section and info >> 4 in (1, 2, 10) and other & 3 == 0:
            exports.add(strings[name : strings.index(b"\0", name)].decode())
    return exports


def macho_exports(data: bytes) -> set[str]:
    """Return the defined external symbols of a thin 64-bit Mach-O file, as C names."""
    symbol_table = 0x2
    exports = set()
    for command, position, _ in macho_load_commands(data):
        if command != symbol_table:
            continue
        symbols, count, strings, _ = struct.unpack_from("<IIII", data, position + 8)
        for index in range(count):
            name, kind = struct.unpack_from("<IB", data, symbols + index * 16)
            # External, not private external, not a debug entry, defined in a section.
            if kind & 0x01 and not kind & 0xF0 and kind & 0x0E == 0x0E:
                end = data.index(b"\0", strings + name)
                exports.add(data[strings + name : end].decode().removeprefix("_"))
    return exports


def exports(path: Path) -> set[str]:
    data = path.read_bytes()
    return elf_exports(data) if native_format(path) == "elf" else macho_exports(data)


class ExportsTest(unittest.TestCase):
    def test_libraries_export_only_their_entry_symbol(self) -> None:
        root = Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"] / FIXTURE
        for probe in PROBES:
            with self.subTest(probe=probe):
                library = root / f"lib{probe.lower()}_native.so"
                self.assertEqual({f"{probe}_probe_init"}, exports(library))


if __name__ == "__main__":
    unittest.main()
