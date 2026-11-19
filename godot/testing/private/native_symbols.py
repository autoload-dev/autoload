"""
Read what links native code with its debug symbols: ELF build IDs and Mach-O UUIDs.

A trimmed copy of the ruleset's build-tool native code reader, so the public inspection
helper carries its own implementation.
"""

import struct
from collections.abc import Iterator

_ELF = b"\x7fELF"
# Little-endian thin files, as Apple's toolchains write them, and universal ones.
_MACHO_THIN = {"cefaedfe", "cffaedfe"}
_MACHO_UNIVERSAL = {"cafebabe", "cafebabf"}


def elf_sections(data: bytes) -> dict[str, memoryview]:
    """Return views of an ELF file's sections by name; those without file data are empty."""
    if data[:4] != _ELF:
        raise ValueError("not an ELF file")
    order = "<" if data[5] == 1 else ">"
    if data[4] == 2:
        (offset,) = struct.unpack_from(order + "Q", data, 0x28)
        size, count, names = struct.unpack_from(order + "HHH", data, 0x3A)
        layout = order + "IIQQQQIIQQ"
    else:
        (offset,) = struct.unpack_from(order + "I", data, 0x20)
        size, count, names = struct.unpack_from(order + "HHH", data, 0x2E)
        layout = order + "IIIIIIIIII"
    # Fields: name, type, flags, address, offset, size, ...
    headers = [
        struct.unpack_from(layout, data, offset + index * size) for index in range(count)
    ]
    table = data[headers[names][4] : headers[names][4] + headers[names][5]]
    nobits = 8
    view = memoryview(data)
    return {
        table[header[0] : table.index(b"\0", header[0])].decode(): view[
            header[4] : header[4] + (0 if header[1] == nobits else header[5])
        ]
        for header in headers
    }


def elf_build_id(sections: dict[str, memoryview]) -> str | None:
    """Return the GNU build ID crash reporters match symbols by, as hex."""
    note = sections.get(".note.gnu.build-id")
    if not note:
        return None
    name_size, desc_size = struct.unpack_from("<II", note)
    start = 12 + (name_size + 3) // 4 * 4
    return note[start : start + desc_size].hex()


def _macho_slices(data: bytes) -> list[tuple[int, int]]:
    """Return the offset and size of each CPU of a little-endian Mach-O file."""
    magic = data[:4].hex()
    if magic in _MACHO_THIN:
        return [(0, len(data))]
    if magic not in _MACHO_UNIVERSAL:
        raise ValueError("not a little-endian Mach-O file")
    if len(data) < 8:
        raise ValueError("Truncated universal header")
    (count,) = struct.unpack_from(">I", data, 4)
    # Fields: CPU type, CPU subtype, offset, size, ...
    layout = ">IIQQII" if magic == "cafebabf" else ">IIIII"
    width = struct.calcsize(layout)
    table = 8 + count * width
    if table > len(data):
        raise ValueError("Truncated universal CPU table")
    slices = []
    for index in range(count):
        _, _, offset, size, *_ = struct.unpack_from(layout, data, 8 + index * width)
        if offset < table or offset + size > len(data):
            raise ValueError("Truncated or overlapping universal slice")
        slices.append((offset, size))
    return slices


def _macho_load_commands(
    data: bytes, offset: int, size: int
) -> Iterator[tuple[int, int]]:
    """Yield the type and offset of each load command of a thin Mach-O file."""
    end = offset + size
    magic = data[offset : offset + 4].hex()
    if magic not in _MACHO_THIN:
        raise ValueError("not a little-endian thin Mach-O file")
    position = offset + (32 if magic == "cffaedfe" else 28)
    if position > end:
        raise ValueError("Truncated Mach-O header")
    count, command_bytes = struct.unpack_from("<II", data, offset + 16)
    commands_end = position + command_bytes
    if commands_end > end:
        raise ValueError("Truncated Mach-O load commands")
    for _ in range(count):
        if position + 8 > commands_end:
            raise ValueError("Truncated Mach-O load command")
        command, length = struct.unpack_from("<II", data, position)
        if length < 8 or position + length > commands_end:
            raise ValueError("Truncated Mach-O load command size")
        yield command, position
        position += length


def macho_uuids(data: bytes) -> list[str]:
    """Return the LC_UUID of each CPU of a thin or universal Mach-O file."""
    uuid_command = 0x1B
    uuids = []
    for offset, size in _macho_slices(data):
        for command, position in _macho_load_commands(data, offset, size):
            if command == uuid_command:
                uuids.append(data[position + 8 : position + 24].hex())
                break
    return uuids
