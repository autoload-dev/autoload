"""
Point each ext_resource of a text scene or resource at the UID of the file it names.

Godot resolves an ext_resource by its uid first and its path second, so a
reference with the file's UID survives the file being moved or renamed. A
file's UID is in its .uid sidecar, in the uid line of its .import file, or in
the header of a text scene or resource.
"""

import struct
from collections.abc import Container, Iterator, Mapping
from pathlib import Path

from tools.godot_files import is_sidecar_named
from tools.resource_graph import file_identities, headings, res_path

TEXT_RESOURCES = (".tscn", ".tres")


def declares_uids(path: str) -> bool:
    """Whether a file may declare UIDs: a sidecar or a text scene or resource."""
    return is_sidecar_named(path) or path.endswith(TEXT_RESOURCES)


def uid_sources(files: dict[str, Path]) -> dict[str, str]:
    """
    Return the texts of the files that may declare UIDs, as known_uids takes them.

    Args:
        files: Files by resource path; only sidecars and text resources are read.
    """
    return {
        path: source.read_text(encoding="utf-8", errors="replace")
        for path, source in files.items()
        if declares_uids(path)
    }


def known_uids(files: dict[str, str], declared: Container[str]) -> dict[str, str]:
    """
    Return the UIDs that files declare, by the resource path of the file they identify.

    Args:
        files: Texts of .uid, .import and text resource files by resource path.
        declared: The project's resource paths; a sidecar identifies only a declared file.
    """
    return {
        owner: uid
        for path, text in files.items()
        for owner, uid, _ in file_identities(path, text, declared)
    }


def _mismatches(
    text: str, scene: str, uids: dict[str, str]
) -> Iterator[tuple[str, str, int, int]]:
    """
    Yield each reference whose uid is not its file's known UID.

    Each is its file's resource path, its known UID and the span its uid
    attribute takes; the span is empty for a missing uid, right after type
    where Godot writes it.
    """
    for heading in headings(text):
        if heading.section != "ext_resource" or "path" not in heading.attrs:
            continue
        try:
            path = res_path(heading.attrs["path"], "res://" + scene).removeprefix(
                "res://"
            )
        except ValueError:
            continue
        known, current = uids.get(path), heading.attrs.get("uid")
        if not known or current == known:
            continue
        if current is None:
            position = heading.ends.get("type", heading.body)
            yield path, known, position, position
        else:
            yield path, known, heading.starts["uid"], heading.ends["uid"]


def reference_updates(
    text: str, scene: str, uids: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    """
    Return what scene's references lack: their descriptions and the UIDs they need.

    Args:
        text: The text scene or resource.
        scene: Its resource path, which relative references resolve against.
        uids: Known UIDs by resource path.
    """
    issues, needed = [], {}
    for path, known, begin, end in _mismatches(text, scene, uids):
        issues.append(f"res://{path} ({'missing' if begin == end else 'stale'})")
        needed[path] = known
    return issues, needed


def with_resource_uids(text: str, scene: str, uids: dict[str, str]) -> str:
    """Return text with each reference's uid set to the named file's UID."""
    parts = []
    start = 0
    for _, known, begin, end in _mismatches(text, scene, uids):
        parts += [
            text[start:begin],
            f' uid="{known}"' if begin == end else f'uid="{known}"',
        ]
        start = end
    return "".join(parts) + text[start:]


# ResourceUID's digits: 'a' to 'z', then '0' to '9' from 'z' on, as Godot's char_count is
# 'z' - 'a' = 25 (core/io/resource_uid.cpp:44-45, 92-111 in Godot 4.7.2).
_UID_BASE = 34


def is_uid(text: str) -> bool:
    """Whether ResourceUID::text_to_id reads an ID from text."""
    digits = text.removeprefix("uid://")
    return (
        text.startswith("uid://")
        and bool(digits)
        and all("a" <= c <= "z" or "0" <= c <= "9" for c in digits)
    )


def uid_to_id(text: str) -> int:
    """Return the number ResourceUID::text_to_id reads from a uid:// text."""
    if not text.startswith("uid://"):
        raise ValueError(f"Not a UID: {text!r}")
    value = 0
    for character in text.removeprefix("uid://"):
        if "a" <= character <= "z":
            digit = ord(character) - ord("a")
        elif "0" <= character <= "9":
            digit = ord(character) - ord("0") + _UID_BASE - 9
        else:
            raise ValueError(f"Not a UID: {text!r}")
        value = (value * _UID_BASE + digit) & 0xFFFFFFFFFFFFFFFF
    return value & 0x7FFFFFFFFFFFFFFF


# The digits ResourceUID::id_to_text writes, by value.
_UID_DIGITS = "abcdefghijklmnopqrstuvwxy012345678"


def id_to_uid(value: int) -> str:
    """Return the uid:// text ResourceUID::id_to_text writes for a non-negative ID."""
    if value < 0:
        raise ValueError(f"Not a resource ID: {value}")
    digits = ""
    while True:
        value, digit = divmod(value, _UID_BASE)
        digits = _UID_DIGITS[digit] + digits
        if not value:
            return "uid://" + digits


def uid_cache(uids: Mapping[str, str]) -> bytes:
    """
    Return the .godot/uid_cache.bin of UIDs by resource path, as Godot's export writes it.

    Its format is ResourceUID::encode_binary_cache's (core/io/resource_uid.cpp:259-272);
    entries are sorted by path, so equal inputs give equal bytes.
    """
    # Godot reads a text that is no UID, such as uid://<invalid>, as no ID and caches none.
    valid = {path: uid for path, uid in uids.items() if is_uid(uid)}
    data = bytearray(struct.pack("<I", len(valid)))
    for path, uid in sorted(valid.items()):
        name = ("res://" + path).encode("utf-8")
        data += struct.pack("<QI", uid_to_id(uid), len(name)) + name
    return bytes(data)
