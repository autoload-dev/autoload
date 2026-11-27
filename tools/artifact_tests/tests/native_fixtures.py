"""Minimal ELF and Mach-O files for the inspectors' tests, as the ruleset's tools keep theirs."""

import struct

_ELF_MACHINES = {"arm64": 183, "x86_64": 62}
_MACHO_CPUS = {"arm64": 0x0100000C, "x86_64": 0x01000007}
# LC_BUILD_VERSION platforms by the SDK names the tools report.
_MACHO_PLATFORMS = {"macos": 1, "ios_device": 2, "ios_simulator": 7}


def elf(build_id: bytes = bytes(4), cpu: str = "arm64") -> bytes:
    """Return a minimal 64-bit ELF file for cpu with a GNU build ID note."""
    note = struct.pack("<III", 4, len(build_id), 3) + b"GNU\0" + build_id
    names = b"\0.note.gnu.build-id\0.shstrtab\0"
    sections = 64 + len(note) + len(names)
    header = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    header += struct.pack(
        "<HHIQQQIHHHHHH", 3, _ELF_MACHINES[cpu], 1, 0, 0, sections, 0, 64, 0, 0, 64, 3, 2
    )
    table = bytes(64)
    table += struct.pack("<IIQQQQIIQQ", 1, 7, 0, 0, 64, len(note), 0, 0, 4, 0)
    table += struct.pack(
        "<IIQQQQIIQQ", 20, 3, 0, 0, 64 + len(note), len(names), 0, 0, 1, 0
    )
    return header + note + names + table


def macho(uuid: bytes | None = None, cpu: str = "arm64", sdk: str | None = None) -> bytes:
    """
    Return a minimal 64-bit Mach-O file for cpu.

    It carries an LC_UUID load command with uuid and an LC_BUILD_VERSION one
    for sdk, such as ios_simulator, when they are given.
    """
    commands = b""
    if uuid is not None:
        commands += struct.pack("<II", 0x1B, 24) + uuid
    if sdk is not None:
        commands += struct.pack("<6I", 0x32, 24, _MACHO_PLATFORMS[sdk], 0, 0, 0)
    count = (uuid is not None) + (sdk is not None)
    header = struct.pack(
        "<IiiIIIII", 0xFEEDFACF, _MACHO_CPUS[cpu], 0, 6, count, len(commands), 0, 0
    )
    return header + commands


def archive(*members: bytes) -> bytes:
    """
    Return a static library of the members, as Apple's libtool writes one.

    A symbol table comes first; every member has a BSD long name preceding its contents.
    """
    result = b"!<arch>\n"
    for index, data in enumerate([struct.pack("<I", 0), *members]):
        name = b"__.SYMDEF SORTED" if index == 0 else b"member%d.o" % index
        # Each name is padded so that the contents start 8-byte aligned.
        name += bytes(-len(name) % 8)
        size = len(name) + len(data)
        header = b"#1/%-13d" % len(name) + b"0".ljust(12) + b"0".ljust(6) * 2
        result += header + b"644".ljust(8) + b"%-10d`\n" % size + name + data
        result += bytes(size % 2)
    return result


def universal(*slices: bytes) -> bytes:
    """Return a universal file of thin Mach-O files or static libraries, in order."""
    offset = 8 + 20 * len(slices)
    table = struct.pack(">II", 0xCAFEBABE, len(slices))
    for data in slices:
        # A static library's slice has the CPU of its objects.
        (cpu,) = struct.unpack_from("<I", data, data.index(b"\xcf\xfa\xed\xfe") + 4)
        table += struct.pack(">IIIII", cpu, 0, offset, len(data), 0)
        offset += len(data)
    return table + b"".join(slices)
