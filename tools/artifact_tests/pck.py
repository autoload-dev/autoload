"""
Read the directory of a Godot 4.7.2+ PCK: its version and the resource paths it packs.

A trimmed copy of the ruleset's build-tool PCK reader, so the public inspection helper
carries its own implementation.
"""

import io
import struct
from typing import IO, Any

_MAGIC = 0x43504447


def _exact(source: IO[bytes], size: int) -> bytes:
    value = source.read(size)
    if len(value) != size:
        raise ValueError("truncated PCK directory")
    return value


def _read(source: IO[bytes], fmt: str) -> tuple[Any, ...]:
    return struct.unpack(fmt, _exact(source, struct.calcsize(fmt)))


def pck_contents(data: bytes) -> dict[str, Any]:
    """Read an unencrypted standalone PCK v4 directory: versions and resource paths."""
    source = io.BytesIO(data)
    magic, version, major, minor, patch, flags = _read(source, "<6I")
    if (
        magic != _MAGIC
        or version != 4
        or major != 4
        or (major, minor, patch) < (4, 7, 2)
        or flags & 5
    ):
        raise ValueError(
            "expected an unencrypted standalone Godot 4.7.2+ PCK v4 without sparse storage"
        )
    (file_base,) = _read(source, "<Q")
    (directory,) = _read(source, "<Q")
    source.seek(directory)
    (count,) = _read(source, "<I")
    paths = []
    for _ in range(count):
        (length,) = _read(source, "<I")
        if length > len(data):
            raise ValueError("PCK path exceeds artifact length")
        path = _exact(source, length).rstrip(b"\0").decode("utf-8")
        offset, size = _read(source, "<QQ")
        _exact(source, 16)  # Per-file MD5, used by Godot at runtime.
        (file_flags,) = _read(source, "<I")
        if file_flags & 1:
            raise ValueError("encrypted PCK files are unsupported by this inspector")
        if file_base + offset + size > len(data):
            raise ValueError("PCK file exceeds artifact length: " + path)
        paths.append(path)
    return {
        "format_version": version,
        "godot_version": f"{major:d}.{minor:d}.{patch:d}",
        "file_count": count,
        "paths": sorted(paths),
    }
