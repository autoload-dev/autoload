"""Empty Godot PCKs for the tests of the tools that write and read packs."""

import struct
from pathlib import Path


def pck_bytes(
    version: int = 4, engine: tuple[int, int, int] = (4, 7, 2), padding: int = 0
) -> bytes:
    """A PCK header with an empty directory at offset 40."""
    return struct.pack("<6IQQI", 0x43504447, version, *engine, 0, 0, 40, 0) + bytes(
        padding
    )


def write_pck(path: Path) -> Path:
    path.write_bytes(pck_bytes(padding=128))
    return path
