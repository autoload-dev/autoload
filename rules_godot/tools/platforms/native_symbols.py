"""
Strip native code or extract its dSYM; other files, such as launcher scripts, pass.

Sections: ELF files, Mach-O files, Slices, Command line.
"""

import argparse
import mmap
import os
import shutil
import struct
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

_ELF = b"\x7fELF"

# Little-endian thin files, as Apple's toolchains write them, and universal ones.
_MACHO_THIN = {"cefaedfe", "cffaedfe"}

_MACHO_UNIVERSAL = {"cafebabe", "cafebabf"}

# A whole file's bytes or a read-only map of it, which reads only what is parsed.
type Binary = bytes | mmap.mmap


def native_format(path: str | Path) -> str | None:
    """Return "elf" or "macho" for native code, None for other files."""
    with open(path, "rb") as file:
        magic = file.read(4)
    if magic == _ELF:
        return "elf"
    return "macho" if magic.hex() in _MACHO_THIN | _MACHO_UNIVERSAL else None


# ==== ELF files ===============================================================


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


def elf_file_build_id(data: bytes) -> str | None:
    """Return the GNU build ID of an ELF file, as hex."""
    return elf_build_id(elf_sections(data))


# ==== Mach-O files ============================================================


def _universal_slices(data: Binary, magic: str) -> list[tuple[int, int]]:
    """Return the offset and size of each CPU of a universal Mach-O file."""
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


def macho_slices(data: Binary) -> list[tuple[int, int]]:
    """
    Return the offset and size of each CPU of a little-endian Mach-O file.

    A thin file is its own single CPU.
    """
    magic = data[:4].hex()
    if magic in _MACHO_THIN:
        return [(0, len(data))]
    if magic not in _MACHO_UNIVERSAL:
        raise ValueError("not a little-endian Mach-O file")
    return _universal_slices(data, magic)


def _macho_header(data: Binary, offset: int, end: int) -> tuple[int, int, int]:
    """Return the load commands' count, start and end of the thin Mach-O file at offset."""
    magic = data[offset : offset + 4].hex()
    if magic not in _MACHO_THIN:
        raise ValueError("not a little-endian thin Mach-O file")
    start = offset + (32 if magic == "cffaedfe" else 28)
    if start > end:
        raise ValueError("Truncated Mach-O header")
    count, command_bytes = struct.unpack_from("<II", data, offset + 16)
    if start + command_bytes > end:
        raise ValueError("Truncated Mach-O load commands")
    return count, start, start + command_bytes


def macho_load_commands(
    data: Binary, offset: int = 0, size: int | None = None
) -> Iterator[tuple[int, int, int]]:
    """Yield the type, offset and size of each load command of a thin Mach-O file."""
    end = len(data) if size is None else offset + size
    count, position, commands_end = _macho_header(data, offset, end)
    for _ in range(count):
        if position + 8 > commands_end:
            raise ValueError("Truncated Mach-O load command")
        command, length = struct.unpack_from("<II", data, position)
        if length < 8 or position + length > commands_end:
            raise ValueError("Truncated Mach-O load command size")
        yield command, position, length
        position += length
    if position != commands_end:
        raise ValueError("Mach-O load commands differ from their declared size")


def macho_uuids(data: Binary) -> list[str]:
    """Return the LC_UUID of each CPU of a thin or universal Mach-O file."""
    uuid_command = 0x1B
    uuids = []
    for offset, size in macho_slices(data):
        for command, position, _ in macho_load_commands(data, offset, size):
            if command == uuid_command:
                uuids.append(data[position + 8 : position + 24].hex())
                break
    return uuids


_MACHO_CPUS = {0x100000C: "arm64", 0x1000007: "x86_64"}

# The load commands that name an SDK: LC_BUILD_VERSION, LC_VERSION_MIN_MACOSX and
# LC_VERSION_MIN_IPHONEOS.
_BUILD_VERSION = 0x32

_VERSION_MIN_MACOS = 0x24

_VERSION_MIN_IOS = 0x25


def _command_sdk(
    data: Binary, load_command: tuple[int, int, int], cpu: str
) -> str | None:
    """Return the Apple SDK that the load command names, or None for an unknown platform."""
    command, position, length = load_command
    if command == _VERSION_MIN_MACOS:
        return "macos"
    if command == _VERSION_MIN_IOS:
        return "ios_device" if cpu == "arm64" else "ios_simulator"
    if length < 24:
        raise ValueError("Truncated Mach-O build version")
    value = struct.unpack_from("<I", data, position + 8)[0]
    return {1: "macos", 2: "ios_device", 7: "ios_simulator"}.get(value)


def _macho_identity(data: Binary, offset: int, size: int) -> tuple[str, str | None]:
    """Return the CPU and Apple SDK, if named, of the thin Mach-O file at offset."""
    if data[offset : offset + 4].hex() != "cffaedfe" or size < 32:
        raise ValueError("Unsupported native binary format")
    cpu_value = struct.unpack_from("<I", data, offset + 4)[0]
    cpu = _MACHO_CPUS.get(cpu_value)
    if not cpu:
        raise ValueError(f"Unsupported Mach-O CPU type {cpu_value}")
    # The last command that names an SDK decides.
    sdk = None
    for load_command in macho_load_commands(data, offset, size):
        if load_command[0] in {_BUILD_VERSION, _VERSION_MIN_MACOS, _VERSION_MIN_IOS}:
            sdk = _command_sdk(data, load_command, cpu)
    return cpu, sdk


def _macho_slice(data: Binary, offset: int, size: int) -> tuple[str, str]:
    """Return the CPU and Apple SDK of the thin Mach-O file at offset."""
    cpu, sdk = _macho_identity(data, offset, size)
    if sdk is None:
        raise ValueError("Missing or unsupported Mach-O SDK")
    return cpu, sdk


# ==== Slices ==================================================================


# ELF e_machine values by Godot's CPU tag; the class (32- or 64-bit) follows the CPU.
_ELF_CPUS = {3: "x86_32", 40: "arm32", 62: "x86_64", 183: "arm64", 243: "rv64"}

_ARCHIVE = b"!<arch>\n"

_MEMBER_HEADER = 60


def _archive_members(data: Binary, offset: int, size: int) -> Iterator[tuple[int, int]]:
    """Yield the offset and size of each member's contents of a static library."""
    end = offset + size
    position = offset + len(_ARCHIVE)
    while position < end:
        header = bytes(data[position : position + _MEMBER_HEADER])
        if len(header) < _MEMBER_HEADER or header[58:] != b"`\n":
            raise ValueError("Truncated or malformed static library member")
        length = int(header[48:58])
        start = position + _MEMBER_HEADER
        if start + length > end:
            raise ValueError("Truncated static library member")
        # A BSD long name, #1/<length>, precedes the member's contents.
        name = header[:16].rstrip()
        skip = int(name[3:]) if name.startswith(b"#1/") else 0
        yield start + skip, length - skip
        position = start + length + length % 2


def _archive_slices(data: Binary, offset: int, size: int) -> dict[str, str]:
    """
    Return the CPUs and SDK of a static library's Mach-O objects.

    Other members, such as its symbol table or LLVM bitcode, name none. An empty
    SDK means that no object of the CPU names one.
    """
    result = {}
    for start, length in _archive_members(data, offset, size):
        if data[start : start + 4].hex() not in _MACHO_THIN:
            continue
        cpu, sdk = _macho_identity(data, start, length)
        known = result.setdefault(cpu, sdk or "")
        if sdk and known != sdk:
            raise ValueError(
                f"Static library objects of {cpu} differ in SDK: {known} and {sdk}"
            )
    return result


def _elf_slice(data: Binary) -> dict[str, tuple[str, int, int]]:
    """
    Return the CPU of an ELF file.

    Its code is the whole file, and "elf" stands in for the SDK.
    """
    if data[4] not in {1, 2} or data[5] not in {1, 2}:
        raise ValueError("Unsupported ELF encoding")
    machine = struct.unpack_from(("<" if data[5] == 1 else ">") + "H", data, 18)[0]
    cpu = _ELF_CPUS.get(machine)
    if not cpu:
        raise ValueError(f"Unsupported ELF machine {machine}")
    return {cpu: ("elf", 0, len(data))}


def _slice_identities(data: Binary, offset: int, size: int) -> dict[str, str]:
    """Return the CPUs and SDK of one slice, a thin Mach-O file or a static library."""
    if data[offset : offset + len(_ARCHIVE)] == _ARCHIVE:
        return _archive_slices(data, offset, size)
    return dict([_macho_slice(data, offset, size)])


def _macho_file_slices(data: Binary) -> dict[str, tuple[str, int, int]]:
    """Return each CPU's SDK and the offset and size of its code in a Mach-O file."""
    if data[:4].hex() not in {"cffaedfe", "cafebabe", "cafebabf"}:
        raise ValueError("Unsupported native binary format")
    result = {}
    for offset, size in macho_slices(data):
        for cpu, sdk in _slice_identities(data, offset, size).items():
            if cpu in result:
                raise ValueError("Duplicate CPU slice")
            result[cpu] = (sdk, offset, size)
    return result


def _slices(data: Binary) -> dict[str, tuple[str, int, int]]:
    """Return each CPU's SDK and the offset and size of its code."""
    if data[: len(_ARCHIVE)] == _ARCHIVE:
        return {
            cpu: (sdk, 0, len(data))
            for cpu, sdk in _archive_slices(data, 0, len(data)).items()
        }
    if len(data) < 20:
        raise ValueError("Truncated native header")
    if data[:4] == _ELF:
        return _elf_slice(data)
    return _macho_file_slices(data)


def native_slices(data: Binary) -> dict[str, str]:
    """
    Read CPU and Apple SDK identity from the binary, independent of its label.

    A static library has those of its objects; an empty identity names no SDK.
    """
    return {cpu: sdk for cpu, (sdk, _, _) in _slices(data).items()}


def require_slices(data: Binary, cpus: set[str], sdk: str, origin: str) -> None:
    """Reject a delivered binary whose CPUs or SDK differ from the requested ones."""
    actual = native_slices(data)
    if set(actual) != cpus:
        raise ValueError(
            f"{origin}: native CPU slices {sorted(actual)} differ from requested {sorted(cpus)}"
        )
    if any(value != sdk for value in actual.values()):
        raise ValueError(f"{origin}: SDKs {actual} differ from {sdk}")


def desktop_runtime(data: bytes, cpu: str, operating_system: str) -> bytes:
    """Select a singleton desktop runtime from a universal binary, then verify it."""
    slices = _slices(data)
    if cpu not in slices:
        raise ValueError(f"Runtime CPU {cpu} is absent from {sorted(slices)}")
    actual, offset, size = slices[cpu]
    sdk = "macos" if operating_system == "macos" else "elf"
    if actual != sdk:
        raise ValueError(f"desktop runtime: SDK of {cpu}: {actual} differs from {sdk}")
    return data[offset : offset + size] if len(slices) > 1 else data


# ==== Command line ============================================================


def strip(tool: str, options: list[str], source: str, output: str) -> None:
    form = native_format(source)
    if form:
        result = subprocess.run(
            [tool, *options, "-o", output, source],
            capture_output=True,
            text=True,
            check=False,
        )
        # The signature is renewed below; other diagnostics stay visible.
        for line in result.stderr.splitlines():
            if "invalidate the code signature" not in line:
                print(line, file=sys.stderr)
        result.check_returncode()
    else:
        shutil.copyfile(source, output)
    os.chmod(output, 0o755)
    if form == "macho":
        # Stripping invalidates the signature, and arm64 Macs run only signed code.
        # The tool signs ad hoc, as the linker does; godot_app can sign the whole bundle.
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--sign", "-", output],
            check=True,
            capture_output=True,
        )


def dsym(source: str, output: str) -> None:
    if native_format(source) == "macho":
        subprocess.run(["/usr/bin/xcrun", "dsymutil", source, "-o", output], check=True)
    else:
        Path(output).mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["strip", "dsym"])
    parser.add_argument("--tool", help="The C/C++ toolchain's strip tool.")
    parser.add_argument("--option", action="append", default=[], help="Strip option.")
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument(
        "--output", action="append", required=True, help="One per --input, in order."
    )
    args = parser.parse_args()
    if len(args.input) != len(args.output):
        parser.error("every --input needs an --output")
    for source, output in zip(args.input, args.output, strict=True):
        if args.mode == "strip":
            strip(args.tool, args.option, source, output)
        else:
            dsym(source, output)


if __name__ == "__main__":
    main()
