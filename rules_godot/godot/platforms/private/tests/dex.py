"""
Read the classes that an Android DEX file defines, for the tests that inspect applications.

It follows the DEX reader of @autoload_dev//tools/artifact_tests:inspect_android_bundle.py,
whose library serves the public inspection helper only.
"""

import struct

# The layout of a standard little-endian DEX file:
# https://source.android.com/docs/core/runtime/dex-format#header-item
HEADER_SIZE = 112
ENDIAN_CONSTANT = 0x12345678
VERSIONS = range(35, 41)


def check_header(dex: bytes) -> None:
    if len(dex) < HEADER_SIZE or dex[:4] != b"dex\n" or dex[7] != 0:
        raise ValueError("Invalid DEX header")
    version = dex[4:7]
    if not version.isdigit() or int(version) not in VERSIONS:
        raise ValueError("Unsupported DEX version")
    size, header_size, endian = struct.unpack_from("<III", dex, 32)
    if (size, header_size, endian) != (len(dex), HEADER_SIZE, ENDIAN_CONSTANT):
        raise ValueError("Invalid DEX size, header or byte order")


def table(dex: bytes, field: int, width: int) -> tuple[int, int]:
    """Return the item count and offset of the table that the header field describes."""
    count, offset = struct.unpack_from("<II", dex, field)
    if count and (offset < HEADER_SIZE or offset + count * width > len(dex)):
        raise ValueError("DEX table outside file")
    return count, offset


def word(dex: bytes, offset: int) -> int:
    return struct.unpack_from("<I", dex, offset)[0]


def string_start(dex: bytes, offset: int) -> int:
    """Skip the ULEB128 UTF-16 length that precedes a string's MUTF-8 bytes."""
    for _ in range(5):
        if offset >= len(dex):
            raise ValueError("DEX string outside file")
        byte = dex[offset]
        offset += 1
        if not byte & 0x80:
            return offset
    raise ValueError("Invalid DEX string length")


def class_name(dex: bytes, offset: int) -> str:
    """Return the class name of the type descriptor at the string's offset."""
    start = string_start(dex, offset)
    end = dex.find(b"\0", start)
    if end < 0:
        raise ValueError("Unterminated DEX descriptor")
    descriptor = dex[start:end].decode("utf-8")
    if not descriptor.startswith("L") or not descriptor.endswith(";"):
        raise ValueError("Invalid DEX class descriptor")
    return descriptor[1:-1].replace("/", ".")


def defined_classes(dex: bytes) -> set[str]:
    """Return the names of the classes that the DEX file's class_defs table defines."""
    check_header(dex)
    string_count, strings = table(dex, 56, 4)
    type_count, types = table(dex, 64, 4)
    class_count, classes = table(dex, 96, 32)
    result = set()
    for index in range(class_count):
        type_index = word(dex, classes + index * 32)
        if type_index >= type_count:
            raise ValueError("DEX class type outside type table")
        string_index = word(dex, types + type_index * 4)
        if string_index >= string_count:
            raise ValueError("DEX descriptor outside string table")
        result.add(class_name(dex, word(dex, strings + string_index * 4)))
    return result
