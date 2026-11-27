"""
The text of Godot resources that build tools read: formats, resource paths, the lexer,
section headings and authored identities.

The graph (resource_graph/graph.py) scans references on top of this; the tools that stage,
validate, index and pack files need only this part, so a change to the graph reruns none
of their actions.

Sections: Formats and paths, Lexer, Text resources, Identities.
"""

import json
import posixpath
import re
import unicodedata
from collections import defaultdict
from collections.abc import Container, Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

# ==== Formats and paths =======================================================


# These are format policies, not a claim that custom loaders cannot attach
# meaning to raw bytes. Only the supported built-in Godot interpretation is
# modeled. In particular JSON/CSV/configuration files and binary scene/model
# formats stay unsupported until a format-specific scanner exists.
ANALYZED_FORMATS = frozenset(
    {
        ".tscn",
        ".tres",
        ".gd",
        ".gdshader",
        ".gdshaderinc",
        ".shader",
        ".shaderinc",
        ".gltf",
        ".uid",
        ".import",
    }
)

LEAF_FORMATS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".tga",
        ".ktx",
        ".exr",
        ".hdr",
        ".dds",
        ".wav",
        ".ogg",
        ".mp3",
        ".ogv",
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".translation",
        ".po",
        ".mo",
        ".bin",
    }
)

# Formats Godot loads that no scanner of the graph reads.
OPAQUE_FORMATS = frozenset(
    {".res", ".scn", ".svg", ".glb", ".obj", ".fbx", ".csv", ".json", ".gdextension"}
)

# The project configuration, which the graph scans for settings that name resources.
PROJECT_FILE = "res://project.godot"


def portable_identity(path: str) -> str:
    """The spelling that case-insensitive, normalizing filesystems compare."""
    return unicodedata.normalize("NFC", path).casefold()


def _project_relative(value: str, source: str) -> str:
    """A reference without its res:// prefix; a relative one is joined to its source's directory."""
    if value.startswith("res://"):
        return value[6:]
    if ":" in value or value.startswith("/"):
        raise ValueError("only resource paths or res:// paths are supported")
    return posixpath.join(posixpath.dirname(source[6:]), value)


def res_path(value: str, source: str = PROJECT_FILE) -> str:
    """Normalize a resource reference, rejecting escapes and non-resource URLs."""
    value = _project_relative(value, source)
    if any(char in value for char in "\\\0:") or value.startswith("/"):
        raise ValueError("invalid resource path")
    value = posixpath.normpath(value)
    if value in ("", ".", "..") or value.startswith("../"):
        raise ValueError("resource path escapes the project")
    return "res://" + value


# ==== Lexer ===================================================================


class Token(NamedTuple):
    category: str
    value: str
    line: int
    # Offsets in the text where the token starts and ends.
    start: int
    end: int


_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "'": "'"}

_UNICODE_ESCAPE = re.compile(r"[0-9a-fA-F]{4}")


def _read_escape(text: str, index: int, raw: bool) -> tuple[str, int]:
    """The text of the escape sequence at text[index], a backslash, and where it ends."""
    escape = text[index + 1]
    if raw:
        return "\\" + escape, index + 2
    if escape in _ESCAPES:
        return _ESCAPES[escape], index + 2
    if escape == "u":
        digits = text[index + 2 : index + 6]
        if _UNICODE_ESCAPE.fullmatch(digits):
            return chr(int(digits, 16)), index + 6
    return "\\" + escape, index + 2


def _starts_string(text: str, index: int) -> bool:
    return text[index] in "\"'" or text.startswith(('r"', "r'"), index)


def _read_string(text: str, start: int) -> tuple[str, bool, int]:
    """The value of the string starting at text[start], whether it is closed, and where it ends."""
    raw = text[start] == "r"
    index = start + 1 if raw else start
    quote = text[index]
    delimiter = quote * (3 if text.startswith(quote * 3, index) else 1)
    index += len(delimiter)
    value = []
    while index < len(text):
        if text.startswith(delimiter, index):
            return "".join(value), True, index + len(delimiter)
        if text[index] == "\\" and index + 1 < len(text):
            decoded, index = _read_escape(text, index, raw)
            value.append(decoded)
        else:
            value.append(text[index])
            index += 1
    return "".join(value), False, index


_WORD = re.compile(r"\w*")


def _identifier_end(text: str, index: int) -> int:
    # \w* matches the empty string, so a match always exists.
    match = _WORD.match(text, index + 1)
    return match.end() if match else index + 1


def _starts_line_comment(text: str, index: int, shader: bool) -> bool:
    """Whether a comment to the end of the line starts at text[index]: // in a shader, # else."""
    return text.startswith("//", index) if shader else text[index] == "#"


def _line_comment_end(text: str, index: int) -> int:
    """Where the comment at text[index] ends: at its line's newline, which it leaves out."""
    end = text.find("\n", index)
    return len(text) if end < 0 else end


def _block_comment_end(text: str, index: int) -> int:
    end = text.find("*/", index + 2)
    return len(text) if end < 0 else end + 2


def _skip_trivia(text: str, index: int, shader: bool) -> int | None:
    """Where the whitespace or comment at text[index] ends; None where a token starts."""
    char = text[index]
    if char != "\n" and char.isspace():
        return index + 1
    if _starts_line_comment(text, index, shader):
        return _line_comment_end(text, index)
    if shader and text.startswith("/*", index):
        return _block_comment_end(text, index)
    return None


def _read_token(text: str, index: int) -> tuple[str, str, int]:
    """The category, value and end of the token starting at text[index]."""
    char = text[index]
    if char == "\n":
        return "newline", char, index + 1
    if _starts_string(text, index):
        value, closed, end = _read_string(text, index)
        return ("string" if closed else "invalid"), value, end
    if char.isalpha() or char == "_":
        end = _identifier_end(text, index)
        return "identifier", text[index:end], end
    return "punctuation", char, index + 1


def lex(text: str, *, shader: bool = False) -> list[Token]:
    """
    Lex strings/comments without mistaking examples in comments for loads.

    This small lexer handles GDScript quoted/raw/multiline strings and shader
    comments. It is intentionally not a GDScript parser or constant evaluator.
    """
    result = []
    index, line = 0, 1
    while index < len(text):
        end = _skip_trivia(text, index, shader)
        if end is None:
            category, value, end = _read_token(text, index)
            result.append(Token(category, value, line, index, end))
        line += text.count("\n", index, end)
        index = end
    return result


def tokens(text: str, *, shader: bool = False) -> list[tuple[str, str, int]]:
    """The tokens of lex as (category, value, line)."""
    return [token[:3] for token in lex(text, shader=shader)]


# ==== Text resources ==========================================================


_SECTION = re.compile(r"^[ \t]*\[([a-z_]+)\b", re.MULTILINE)

_KEY = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")

_CLOSING = {"(": ")", "[": "]", "{": "}"}

_ASSIGN = re.compile(r"\s*=\s*")


class Heading(NamedTuple):
    """A section heading of a text scene or resource, such as `[node name="Main"]`."""

    section: str
    # Attribute values, strings decoded.
    attrs: dict[str, str]
    # Offsets in the text where each attribute starts and its value ends.
    starts: dict[str, int]
    ends: dict[str, int]
    # Offsets after the section name and of the closing bracket.
    body: int
    end: int
    line: int


def _quote_end(text: str, index: int) -> int:
    """Where a quoted value ends: at its closing quote, or the end of the text."""
    while index < len(text) and text[index] != '"':
        index += 2 if text[index] == "\\" else 1
    return index


def _in_value(text: str, index: int, depth: list[str]) -> bool:
    """Whether text[index] belongs to a heading attribute's value: it ends at a separator."""
    if index >= len(text):
        return False
    return bool(depth) or text[index] not in " \t\n]"


def _value_end(text: str, index: int) -> int:
    """Return where a heading attribute's value starting at index ends."""
    depth: list[str] = []
    while _in_value(text, index, depth):
        char = text[index]
        if char == '"':
            index = _quote_end(text, index + 1)
        elif char in _CLOSING:
            depth.append(_CLOSING[char])
        elif depth and char == depth[-1]:
            depth.pop()
        index += 1
    return index


def _skip_blanks(text: str, index: int) -> int:
    """The index of the first character from text[index] on that is no space or tab."""
    while index < len(text) and text[index] in " \t":
        index += 1
    return index


def _attribute_start(text: str, index: int) -> tuple[re.Match[str], re.Match[str]] | None:
    """The key and the equals sign of the heading attribute at text[index], if there is one."""
    key = _KEY.match(text, index)
    if key is None:
        return None
    equals = _ASSIGN.match(text, key.end())
    return None if equals is None else (key, equals)


def _read_attributes(
    text: str, index: int
) -> tuple[dict[str, str], dict[str, int], dict[str, int], int]:
    """
    Read the attributes of a heading from text[index].

    Returns their values, the offsets where each key starts and its value ends,
    and the offset where the attributes stop.
    """
    attrs: dict[str, str] = {}
    starts: dict[str, int] = {}
    ends: dict[str, int] = {}
    while True:
        index = _skip_blanks(text, index)
        if text[index : index + 1] in ("", "]"):
            break
        found = _attribute_start(text, index)
        if found is None:
            break
        key, equals = found
        value = text[equals.end() : _value_end(text, equals.end())]
        attrs[key[0]] = tokens(value)[0][1] if value.startswith('"') else value
        starts[key[0]], ends[key[0]] = key.start(), equals.end() + len(value)
        index = ends[key[0]]
    return attrs, starts, ends, index


def headings(text: str) -> Iterator[Heading]:
    """
    Yield the section headings of a text scene or resource.

    Quoted values may contain brackets and escaped quotes, and unquoted ones
    nested brackets; a malformed heading is skipped.
    """
    line, counted = 1, 0
    for match in _SECTION.finditer(text):
        attrs, starts, ends, index = _read_attributes(text, match.end())
        if text[index : index + 1] != "]":
            continue
        line += text.count("\n", counted, match.start())
        counted = match.start()
        yield Heading(match[1], attrs, starts, ends, match.end(), index, line)


# A remap key naming an imported file: path, or path.<feature> for a feature's variant.
REMAP_PATH = re.compile(
    r'^(path(?:\.([A-Za-z0-9_]+))?)="res://([^"]+)"[ \t]*$', re.MULTILINE
)

IMPORTER = re.compile(r'^importer="([^"]*)"', re.MULTILINE)


def remap_section(text: str) -> str | None:
    """The [remap] section of an .import file, up to the next section; None without one."""
    starts = [
        (heading.section, text.rfind("[", 0, heading.body)) for heading in headings(text)
    ]
    remap = next((start for section, start in starts if section == "remap"), None)
    if remap is None:
        return None
    end = next((start for _, start in starts if start > remap), len(text))
    return text[remap:end]


def gd_string(value: str) -> str:
    """A Godot string literal of value."""
    return json.dumps(value, ensure_ascii=False)


# ==== Identities ==============================================================


UID = re.compile(r"uid://[a-z0-9]+")

_IMPORT_UID = re.compile(r'^\s*uid\s*=\s*"(uid://[a-z0-9]+)"', re.MULTILINE)


def file_identities(
    path: str, text: str, declared: Container[str]
) -> list[tuple[str, str, int]]:
    """
    Return (owner, uid, line) authored by one file.

    External-resource UIDs are references, not owners. A sidecar authors the
    identity of its declared source.
    """
    lower = path.lower()
    if lower.endswith((".tscn", ".tres")):
        # The file descriptor is the first section and alone carries identity.
        for heading in headings(text):
            return (
                [(path, heading.attrs["uid"], heading.line)]
                if heading.section in {"gd_scene", "gd_resource"}
                and heading.attrs.get("uid")
                else []
            )
    elif lower.endswith(".uid") and path[:-4] in declared:
        return [(path[:-4], text.strip(), 0)]
    elif lower.endswith(".import") and path[:-7] in declared:
        return [
            (path[:-7], match[1], text.count("\n", 0, match.start()) + 1)
            for match in _IMPORT_UID.finditer(text)
        ]
    return []


def _descriptor(source: Path) -> str:
    """Read a scene or resource only up to its first section heading."""
    lines = []
    with source.open(encoding="utf-8") as stream:
        for line in stream:
            lines.append(line)
            if line.lstrip().startswith("["):
                break
    return "".join(lines)


def authored_identities(resource_paths: dict[str, Path]) -> dict[str, set[str]]:
    """Collect authored IDs of declared files, reading only what carries them."""
    identities = defaultdict(set)
    normalized = {res_path(path): source for path, source in resource_paths.items()}
    for path, source in sorted(normalized.items()):
        lower = path.lower()
        if lower.endswith((".tscn", ".tres")):
            text = _descriptor(source)
        elif lower.endswith((".uid", ".import")):
            text = source.read_text(encoding="utf-8")
        else:
            continue
        for owner, uid, _ in file_identities(path, text, normalized):
            identities[uid].add(owner)
    return identities


def _check_authored(uid: str, paths: set[str]) -> None:
    if not UID.fullmatch(uid):
        raise ValueError("Invalid authored resource UID: " + uid)
    if len(paths) > 1:
        raise ValueError(
            "Duplicate authored resource UID " + uid + ": " + ", ".join(sorted(paths))
        )


def _uids_by_resource(
    identities: Iterable[tuple[str, set[str]]],
) -> defaultdict[str, set[str]]:
    by_resource = defaultdict(set)
    for uid, paths in identities:
        for path in paths:
            by_resource[path].add(uid)
    return by_resource


def _check_conflicting(by_resource: dict[str, set[str]]) -> None:
    for path, values in sorted(by_resource.items()):
        if len(values) > 1:
            raise ValueError(
                "Conflicting authored resource UIDs for "
                + path
                + ": "
                + ", ".join(sorted(values))
            )


def validate_identities(resource_paths: dict[str, Path]) -> None:
    """Reject invalid/duplicate authored UID ownership for staged action inputs."""
    identities = sorted(authored_identities(resource_paths).items())
    for uid, paths in identities:
        _check_authored(uid, paths)
    _check_conflicting(_uids_by_resource(identities))
