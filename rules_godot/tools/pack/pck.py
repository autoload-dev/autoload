"""
Read and write Godot 4.7.2+ PCKs: their directory, members and packed project settings.

Sections: Reading, Writing, Project settings.
"""

import functools
import hashlib
import io
import os
import re
import struct
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from tools.resources.files import EXTENSION_LIST

_MAGIC = 0x43504447


# ==== Reading =================================================================


@dataclass(frozen=True)
class _Entry:
    path: str
    offset: int  # Absolute position of the file's bytes.
    size: int
    md5: bytes
    flags: int


def _exact(source: IO[bytes], size: int) -> bytes:
    value = source.read(size)
    if len(value) != size:
        raise ValueError("truncated PCK directory")
    return value


def _content(source: IO[bytes], entry: _Entry) -> bytes:
    position = source.tell()
    source.seek(entry.offset)
    data = _exact(source, entry.size)
    source.seek(position)
    return data


def _read(source: IO[bytes], fmt: str) -> tuple[Any, ...]:
    return struct.unpack(fmt, _exact(source, struct.calcsize(fmt)))


# The header flags of an encrypted directory (1) and of sparse storage (4), which this
# module cannot read.
_ENCRYPTED_OR_SPARSE = 1 | 4


def _is_supported(header: tuple[int, ...]) -> bool:
    """Whether a header's six words name a Godot 4.7.2+ PCK v4 that this module reads."""
    magic, version, major, minor, patch, flags = header
    if (magic, version, major) != (_MAGIC, 4, 4) or (minor, patch) < (7, 2):
        return False
    return not flags & _ENCRYPTED_OR_SPARSE


def _entry(source: IO[bytes], file_size: int, file_base: int) -> _Entry:
    """Read the directory entry at the source's position."""
    (length,) = _read(source, "<I")
    if length > file_size:
        raise ValueError("PCK path exceeds artifact length")
    path = _exact(source, length).rstrip(b"\0").decode("utf-8")
    offset, size = _read(source, "<QQ")
    md5 = _exact(source, 16)  # Per-file MD5, used by Godot at runtime.
    (flags,) = _read(source, "<I")
    if flags & 1:
        raise ValueError("encrypted PCK files are unsupported by this inspector")
    if file_base + offset + size > file_size:
        raise ValueError("PCK file exceeds artifact length: " + path)
    return _Entry(path, file_base + offset, size, md5, flags)


def _directory(source: IO[bytes], file_size: int) -> tuple[bytes, list[_Entry]]:
    """Return a PCK's header up to its directory offset and its directory entries."""
    header = _read(source, "<6I")
    if not _is_supported(header):
        raise ValueError(
            "expected an unencrypted standalone Godot 4.7.2+ PCK v4 without sparse storage"
        )
    file_base, directory = _read(source, "<QQ")
    source.seek(directory)
    (count,) = _read(source, "<I")
    entries = [_entry(source, file_size, file_base) for _ in range(count)]
    return struct.pack("<6I", *header), entries


def _pck_contents(
    source: IO[bytes], file_size: int, include_paths: bool
) -> dict[str, Any]:
    header, entries = _directory(source, file_size)
    _, version, major, minor, patch, _ = struct.unpack("<6I", header)
    descriptors = {}
    extension_list = []
    for entry in entries:
        if entry.path.endswith(".gdextension"):
            descriptors[entry.path] = _content(source, entry).decode("utf-8")
        elif entry.path == EXTENSION_LIST:
            extension_list = _content(source, entry).decode("utf-8").splitlines()
    return {
        "format_version": version,
        "godot_version": f"{major:d}.{minor:d}.{patch:d}",
        "file_count": len(entries),
        "extension_descriptors": descriptors,
        "extension_list": [line for line in extension_list if line.strip()],
        **({"paths": sorted(entry.path for entry in entries)} if include_paths else {}),
    }


def pck_contents(data: bytes, include_paths: bool = False) -> dict[str, Any]:
    """Read a Godot 4.7.2+ unencrypted standalone PCK v4 directory."""
    return _pck_contents(io.BytesIO(data), len(data), include_paths)


def pck_file_contents(
    path: str | os.PathLike[str], include_paths: bool = False
) -> dict[str, Any]:
    """Inspect a PCK directory without loading all asset contents into memory."""
    with Path(path).open("rb") as source:
        return _pck_contents(source, Path(path).stat().st_size, include_paths)


def _member(source: IO[bytes], file_size: int, path: str) -> bytes:
    _, entries = _directory(source, file_size)
    name = path.removeprefix("res://")
    for entry in entries:
        if entry.path.removeprefix("res://") == name:
            return _content(source, entry)
    raise KeyError(f"PCK has no file {path}")


def pck_member(data: bytes, path: str) -> bytes:
    """Return the bytes of a packed file by its path, with or without res://."""
    return _member(io.BytesIO(data), len(data), path)


def pck_file_member(source: str | os.PathLike[str], path: str) -> bytes:
    """Return one packed file without loading the other asset contents into memory."""
    with Path(source).open("rb") as pack:
        return _member(pack, Path(source).stat().st_size, path)


# ==== Writing =================================================================


# Godot aligns the first file, every file's end and the directory to 16 bytes.
_PADDING = 16

# Two blocks of eight reserved 32-bit words follow the directory offset.
_RESERVED = 64


def _pad(destination: IO[bytes]) -> None:
    destination.write(bytes(-destination.tell() % _PADDING))


# A file to write: its bytes, or a function that opens a stream of them.
Content = bytes | Callable[[], AbstractContextManager[IO[bytes]]]

_CHUNK = 1 << 20


def _copy(out: IO[bytes], original: IO[bytes], entry: _Entry) -> tuple[int, bytes, int]:
    """Copy an entry's bytes from the original PCK; return its size, MD5 and flags."""
    original.seek(entry.offset)
    remaining = entry.size
    while remaining:
        chunk = _exact(original, min(remaining, _CHUNK))
        out.write(chunk)
        remaining -= len(chunk)
    return entry.size, entry.md5, entry.flags


def _write_content(out: IO[bytes], content: Content) -> tuple[int, bytes, int]:
    """Write a file's content; return its size, MD5 and flags."""
    if isinstance(content, bytes):
        content = functools.partial(io.BytesIO, content)
    digest = hashlib.md5()
    size = 0
    with content() as data:
        while chunk := data.read(_CHUNK):
            out.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return size, digest.digest(), 0


def _write_directory(out: IO[bytes], directory: list[tuple]) -> None:
    """Write a directory of each file's path, offset, size, MD5 and flags."""
    out.write(struct.pack("<I", len(directory)))
    for name, offset, size, md5, flags in directory:
        padded = name + bytes(-len(name) % 4)
        out.write(struct.pack("<I", len(padded)) + padded)
        out.write(struct.pack("<QQ", offset, size) + md5 + struct.pack("<I", flags))


def _write(
    out: IO[bytes],
    header: bytes,
    files: Mapping[str, Content | _Entry],
    original: IO[bytes] | None = None,
) -> None:
    """Write a PCK of files sorted by path; an _Entry is copied from original."""
    out.write(header)
    offsets = out.tell()
    out.write(bytes(16 + _RESERVED))
    _pad(out)
    file_base = out.tell()
    directory = []
    for path in sorted(files, key=lambda path: path.encode("utf-8")):
        item = files[path]
        offset = out.tell() - file_base
        if isinstance(item, _Entry):
            assert original is not None
            size, md5, flags = _copy(out, original, item)
        else:
            size, md5, flags = _write_content(out, item)
        _pad(out)
        directory.append((path.encode("utf-8"), offset, size, md5, flags))
    directory_offset = out.tell()
    _write_directory(out, directory)
    out.seek(offsets)
    out.write(struct.pack("<QQ", file_base, directory_offset))


def engine_version(version: str) -> tuple[int, int, int]:
    """Return the numbers a PCK header holds for an engine version such as 4.8.0-beta1."""
    match = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", version)
    if match is None:
        raise ValueError(f"Not a Godot version: {version!r}")
    return int(match[1]), int(match[2]), int(match[3] or 0)


def write_pck(
    destination: str | os.PathLike[str],
    files: Mapping[str, Content],
    version: tuple[int, int, int],
) -> None:
    """
    Write an unencrypted standalone PCK v4 of files, as Godot writes one.

    Entries are sorted by path, so equal inputs give equal bytes.

    Args:
        destination: The PCK to write.
        files: Paths without res:// to their content.
        version: The Godot version the PCK names, at least 4.7.2.
    """
    if version < (4, 7, 2):
        raise ValueError("PCK v4 needs Godot 4.7.2 or later")
    header = struct.pack("<6I", _MAGIC, 4, *version, 0)
    with Path(destination).open("wb") as out:
        _write(out, header, files)


def add_pck_files(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    files: Mapping[str, bytes],
) -> None:
    """
    Write source's PCK with files added to destination, as Godot writes a PCK.

    A file replaces the source's entry of the same path. Entries stay sorted
    by path, so equal inputs give equal bytes.
    """
    with Path(source).open("rb") as original, Path(destination).open("wb") as out:
        header, entries = _directory(original, Path(source).stat().st_size)
        kept: dict[str, Content | _Entry] = {entry.path: entry for entry in entries}
        kept.update(files)
        _write(out, header, kept, original)


def pck_files(source: str | os.PathLike[str]) -> dict[str, bytes]:
    """Return every packed file's bytes by path; for small PCKs such as a configuration's."""
    with Path(source).open("rb") as pack:
        _, entries = _directory(pack, Path(source).stat().st_size)
        return {entry.path: _content(pack, entry) for entry in entries}


# ==== Project settings ========================================================


def _ecfg_field(source: IO[bytes], end: int, name: str) -> bytes:
    """Read a record's field, its size first; name says which field in the error."""
    (size,) = _read(source, "<I")
    if size > end - source.tell():
        raise ValueError(f"ECFG {name} exceeds record bounds")
    return _exact(source, size)


def _ecfg_records(data: bytes) -> Iterator[tuple[str, bytes, bytes]]:
    """Yield each ECFG record's key, encoded Variant value and whole record bytes."""
    source = io.BytesIO(data)
    if _exact(source, 4) != b"ECFG":
        raise ValueError("Expected Godot ECFG project settings")
    (count,) = _read(source, "<I")
    if count > len(data) // 8:
        raise ValueError("ECFG record count exceeds its length")
    for _ in range(count):
        start = source.tell()
        key = _ecfg_field(source, len(data), "key").decode("utf-8")
        value = _ecfg_field(source, len(data), "value")
        yield key, value, data[start : source.tell()]
    if source.tell() != len(data):
        raise ValueError("Trailing ECFG records")


# The Variant type of a String.
_STRING = 4


def _feature_string(value: bytes) -> list[str]:
    """The features of an encoded _custom_features value, a Variant String."""
    if len(value) < 8:
        raise ValueError("Truncated ECFG feature string")
    variant_type, length = struct.unpack_from("<II", value)
    if variant_type != _STRING or len(value) != 8 + length + (-length % 4):
        raise ValueError("Unsupported ECFG feature string encoding")
    if any(value[8 + length :]):
        raise ValueError("Invalid ECFG feature string padding")
    return value[8 : 8 + length].decode("utf-8").split(",")


def _custom_features(data: bytes) -> tuple[list[str], list[bytes], int] | None:
    """
    Return ECFG's custom features, its other records and the features' position.

    The features are in the order Godot wrote them; None means ECFG has none.
    """
    features = None
    position = 0
    records = []
    for key, value, record in _ecfg_records(data):
        if key != "_custom_features":
            records.append(record)
        elif features is not None:
            raise ValueError("Duplicate ECFG _custom_features record")
        else:
            features = _feature_string(value)
            position = len(records)
    return None if features is None else (features, records, position)


def project_setting_keys(data: bytes) -> set[str]:
    """Return the keys of packed ECFG project settings, feature overrides included."""
    return {key for key, _, _ in _ecfg_records(data)}


def project_features(data: bytes) -> set[str]:
    """Return the custom features packed ECFG project settings declare."""
    found = _custom_features(data)
    return set(found[0]) if found else set()


def _without_synthesized(features: list[str], synthesized: set[str]) -> list[str]:
    """The features without one occurrence of each synthesized CPU tag."""
    missing = synthesized - set(features)
    if missing:
        raise ValueError(
            "Synthesized CPU tags absent from ECFG: " + ", ".join(sorted(missing))
        )
    # Godot 4.7 and 4.8 append the plugins' features after the preset's and keep
    # duplicates in ECFG. Only the preset's occurrence goes, so that a plugin's
    # later occurrence still reaches the structural-conflict validation.
    remaining = list(features)
    for tag in synthesized:
        remaining.remove(tag)
    return remaining


def _string_record(key: bytes, text: bytes) -> bytes:
    """An ECFG record whose value is a Variant String."""
    value = struct.pack("<II", _STRING, len(text)) + text + bytes(-len(text) % 4)
    return struct.pack("<I", len(key)) + key + struct.pack("<I", len(value)) + value


def normalize_project_features(data: bytes, synthesized: set[str]) -> bytes:
    """Remove synthesized CPU tags from ECFG while keeping other Variant records opaque."""
    if not synthesized:
        return data
    if not synthesized <= {"arm64", "x86_64"}:
        raise ValueError("Only supported CPU tags may be synthesized")
    found = _custom_features(data)
    if found is None:
        raise ValueError("Missing ECFG custom features")
    features, records, position = found
    kept = ",".join(_without_synthesized(features, synthesized)).encode("utf-8")
    if kept:
        records.insert(position, _string_record(b"_custom_features", kept))
    return b"ECFG" + struct.pack("<I", len(records)) + b"".join(records)
