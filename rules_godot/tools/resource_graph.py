"""
Bounded static Godot reference analysis; never discovers Bazel action inputs.

Graph paths are res:// identities, not execroot paths. The scanner deliberately
does not execute Godot, scripts, importers, or addon code. Unknown dynamic loads
remain diagnostics and must be covered by explicit declarations.
"""

import argparse
import json
import posixpath
import re
import sys
import unicodedata
from collections import defaultdict, deque
from collections.abc import Container, Iterable, Iterator, Sequence
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple
from urllib.parse import unquote, urlsplit

from godot.private.project_config import statement_groups
from tools.godot_files import DIRECTORY_MARKERS, hidden_by

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


# Files godot_build_files collects without a reference scanner.
OPAQUE_FORMATS = frozenset(
    {".res", ".scn", ".svg", ".glb", ".obj", ".fbx", ".csv", ".json", ".gdextension"}
)

# Built-in loaders of these unanalyzed formats resolve further resources; the
# graph records that as a reference it cannot determine.
UNANALYZED_CONTAINERS = frozenset({".res", ".scn"})

# FileAccess reads a file's bytes; file_exists only probes for it.
_FILE_READS = frozenset(
    {
        "open",
        "open_compressed",
        "open_encrypted",
        "open_encrypted_with_pass",
        "get_file_as_bytes",
        "get_file_as_string",
    }
)
_DIRECTORY_LISTINGS = frozenset({"open", "get_files_at", "get_directories_at"})

# Code can guard these runtime accesses, so an unavailable target is not
# necessarily an error. Every other reference must resolve wherever it loads.
SOFT_REFERENCE_KINDS = frozenset({"load", "file_access", "runtime", "runtime_deps"})
# Godot records no file or directory hint for a setting, and a declared runtime
# reference names what code lists. Every other kind loads or reads one file.
DIRECTORY_REFERENCE_KINDS = frozenset({"project_setting", "runtime"})

# The project configuration, which the graph scans for settings that name resources.
_PROJECT_FILE = "res://project.godot"

_UID = re.compile(r"uid://[a-z0-9]+")
_IMPORT_UID = re.compile(r'^\s*uid\s*=\s*"(uid://[a-z0-9]+)"', re.MULTILINE)


def portable_identity(path: str) -> str:
    """The spelling that case-insensitive, normalizing filesystems compare."""
    return unicodedata.normalize("NFC", path).casefold()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def diagnostic(code: str, path: str, message: str, line: int = 0) -> dict:
    """An error finding; warning has the same fields with that severity."""
    return {
        "code": code,
        "path": path,
        "line": line,
        "severity": "error",
        "message": message,
    }


def warning(code: str, path: str, message: str, line: int = 0) -> dict:
    return dict(diagnostic(code, path, message, line), severity="warning")


def format_diagnostic(item: dict) -> str:
    return "{path}:{line}: {severity}: {code}: {message}".format(**item)


def _sorted_diagnostics(diagnostics: list[dict]) -> list[dict]:
    return sorted(
        diagnostics,
        key=lambda item: (item["path"], item["line"], item["code"], item["message"]),
    )


def _record_manifest_line(manifest: dict, kind: str, fields: list) -> None:
    if kind == "project_file":
        manifest["project_file"] = fields[0]
    elif kind == "addon":
        manifest["addons"][fields[0]] = fields[1]
    elif kind == "uses":
        manifest["addon_uses"][fields[0]] = fields[1]
    elif kind == "metadata_index":
        manifest["metadata_index"] = dict(zip(("path", "corrects"), fields))
    elif kind == "ignored":
        manifest["ignored"].append(fields[0])
    elif kind == "relationship":
        manifest["relationships"].append(
            dict(zip(("source", "target", "kind", "owner"), fields))
        )
    else:
        relative, source, owner = fields
        prefix = "import_" if kind == "import" else "member_"
        manifest[prefix + "resource_paths"][relative] = source
        manifest[prefix + "owners"][relative] = owner


def read_manifest(path: Path) -> dict:
    """Read the JSON-lines scan manifest that godot_project writes."""
    manifest = {
        "member_resource_paths": {},
        "import_resource_paths": {},
        "member_owners": {},
        "import_owners": {},
        "relationships": [],
        "ignored": [],
        "addons": {},
        "addon_uses": {},
    }
    for line in path.read_text(encoding="utf-8").splitlines():
        kind, *fields = json.loads(line)
        _record_manifest_line(manifest, kind, fields)
    return manifest


def _chain(parents: dict, path: str | None) -> list[str]:
    """The path from a root to path, following each file's parent."""
    result = []
    while path is not None:
        result.append(path)
        path = parents.get(path)
    return result[::-1]


def _project_relative(value: str, source: str) -> str:
    """A reference without its res:// prefix; a relative one is joined to its source's directory."""
    if value.startswith("res://"):
        return value[6:]
    if ":" in value or value.startswith("/"):
        raise ValueError("only resource paths or res:// paths are supported")
    return posixpath.join(posixpath.dirname(source[6:]), value)


def res_path(value: str, source: str = _PROJECT_FILE) -> str:
    """Normalize a resource reference, rejecting escapes and non-resource URLs."""
    value = _project_relative(value, source)
    if any(char in value for char in "\\\0:") or value.startswith("/"):
        raise ValueError("invalid resource path")
    value = posixpath.normpath(value)
    if value in ("", ".", "..") or value.startswith("../"):
        raise ValueError("resource path escapes the project")
    return "res://" + value


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


def _code_tokens(text: str, *, shader: bool = False) -> list[tuple[str, str, int]]:
    """The tokens of lex without its newlines."""
    return [token for token in tokens(text, shader=shader) if token[0] != "newline"]


_NO_TOKEN = ("", "", 0)


def _at(script: list, i: int) -> tuple[str, str, int]:
    """The token at script[i], or an empty one outside the script."""
    return script[i] if 0 <= i < len(script) else _NO_TOKEN


def _literal_argument(
    script: list, paren: int, closers: Container[str] = (")", ",")
) -> str | None:
    """The first argument of the call opened at script[paren], if it is a lone string literal."""
    if _at(script, paren)[1] != "(":
        return None
    literal, closer = _at(script, paren + 1), _at(script, paren + 2)
    return literal[1] if literal[0] == "string" and closer[1] in closers else None


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
    if not _UID.fullmatch(uid):
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


class _Findings:
    """Collects the findings of a pass over the files of a project."""

    def __init__(self) -> None:
        self.diagnostics: list[dict] = []

    def error(self, code: str, path: str, message: str, line: int = 0) -> None:
        self.diagnostics.append(diagnostic(code, path, message, line))

    def warn(self, code: str, path: str, message: str, line: int = 0) -> None:
        self.diagnostics.append(warning(code, path, message, line))


class _Scan(_Findings):
    """What build_graph collects from the declared files of a project."""

    def __init__(self, execroot: Path) -> None:
        super().__init__()
        self.execroot = execroot
        self.nodes: dict[str, dict] = {}
        self.texts: dict[str, str] = {}
        self.scripts: dict[str, list[tuple[str, str, int]]] = {}
        self.uids: defaultdict[str, set[str]] = defaultdict(set)
        self.classes: defaultdict[str, set[str]] = defaultdict(set)
        self.edges: list[dict] = []

    def reference(
        self,
        source: str,
        target: str | None,
        kind: str,
        line: int = 0,
        uid: str | None = None,
        origin: str = "inferred",
    ) -> None:
        self.edges.append(
            {
                "source": source,
                "reference": target,
                "kind": kind,
                "line": line,
                "uid": uid,
                "origin": origin,
            }
        )


def _targets(edge: dict) -> list[str]:
    """The nodes a resolved edge reaches: its file, or every node below its directory."""
    return edge.get("targets", [edge["target"]])


def _undeclared_addon_use(
    edge: dict, nodes: dict, addon_of: dict, uses: dict
) -> dict | None:
    """The warning for a content file that refers to a file of an add-on it does not use."""
    if edge["status"] != "resolved":
        return None
    source_owner = nodes[edge["source"]].get("owner", "")
    if not source_owner or source_owner in addon_of:
        return None
    for target in _targets(edge):
        label = addon_of.get(nodes.get(target, {}).get("owner", ""))
        if label and label not in uses.get(source_owner, set()):
            return warning(
                "undeclared_addon_use",
                edge["source"],
                f"{edge['kind']} refers to {target} of the add-on {label}; "
                f"list the add-on in the deps of {source_owner}",
                edge["line"],
            )
    return None


def _diagnose_undeclared_addon_uses(
    manifest: dict, scan: _Scan, edges: list[dict]
) -> None:
    """
    Report a content file referring to an add-on's file while its resources use no such add-on.

    The manifest names the operation's add-ons with the owners of their files, and per
    resources owner the add-ons that target and its dependencies use (FR-026). The content
    validation already fails such a script or scene; this names the add-on, for text
    resources too. An add-on's own files are checked by its declaration. It is a warning;
    require_declared makes it an error, as research-addons R9 has it.
    """
    addon_of = {
        owner: label
        for label, owners in manifest.get("addons", {}).items()
        for owner in owners
    }
    uses = {
        owner: set(labels) for owner, labels in manifest.get("addon_uses", {}).items()
    }
    for edge in edges:
        finding = _undeclared_addon_use(edge, scan.nodes, addon_of, uses)
        if finding:
            scan.diagnostics.append(finding)


def _declared_sources(manifest: dict, scan: _Scan) -> tuple[dict, dict]:
    """The project's files by relative path: every declared one, and the members among them."""
    members = dict(manifest.get("member_resource_paths", {}))
    sources = dict(manifest.get("import_resource_paths", {}))
    conflicting = [
        path for path, source in members.items() if sources.get(path, source) != source
    ]
    for path in conflicting:
        scan.error(
            "path_collision",
            res_path(path),
            "import input and project member identify different source files",
        )
    sources.update(members)
    project_file = manifest.get("project_file")
    if project_file:
        if sources.get("project.godot", project_file) != project_file:
            scan.error(
                "path_collision",
                _PROJECT_FILE,
                "project_file conflicts with the declared resource",
            )
        sources["project.godot"] = members["project.godot"] = project_file
    return sources, members


def _owner(manifest: dict, relative: str) -> str | None:
    """The target that declared a file, as a member or else as an import input."""
    return manifest.get("member_owners", {}).get(relative) or manifest.get(
        "import_owners", {}
    ).get(relative)


def _analysis(path: str, suffix: str, ignored: bool) -> str:
    """How the scanner treats a file: analyzed, leaf, unsupported or ignored."""
    if ignored:
        # Godot never scans it; code may read it through FileAccess from the sources.
        return "ignored"
    if suffix in ANALYZED_FORMATS or path == _PROJECT_FILE:
        return "analyzed"
    return "leaf" if suffix in LEAF_FORMATS else "unsupported"


def _flag_format(scan: _Scan, path: str, suffix: str, analysis: str) -> None:
    """Record what the scanner cannot see of a file because of its format."""
    if analysis == "unsupported":
        scan.warn(
            "unsupported_reference_format",
            path,
            "no reference scanner for "
            + (suffix or "extensionless files")
            + "; explicit declarations remain usable but inferred coverage is incomplete",
        )
    if suffix in UNANALYZED_CONTAINERS and analysis != "ignored":
        scan.reference(path, None, "binary_resource")


def _read_text(scan: _Scan, path: str, source: str) -> None:
    try:
        scan.texts[path] = (scan.execroot / source).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        scan.error("unreadable_source", path, str(error))


def _declare_nodes(scan: _Scan, manifest: dict, sources: dict, members: set[str]) -> None:
    """Create the node of each declared file, and read the text of those the scanner analyzes."""
    # The declaring targets decided which files Godot ignores.
    ignored = set(manifest.get("ignored", []))
    folded: dict[str, str] = {}
    for relative, source in sorted(sources.items()):
        path = res_path(relative)
        if path in scan.nodes:
            scan.error(
                "path_collision",
                path,
                "multiple declared paths normalize to the same resource",
            )
            continue
        key = portable_identity(path)
        earlier = folded.get(key, path)
        if earlier != path:
            scan.error(
                "case_collision",
                path,
                "resource differs only in case or Unicode normalization from " + earlier,
            )
        folded[key] = path
        suffix = PurePosixPath(path).suffix.lower()
        analysis = _analysis(path, suffix, relative in ignored)
        node = scan.nodes[path] = {
            "path": path,
            "format": suffix.lstrip("."),
            "uids": [],
            "membership": path in members,
            "analysis": analysis,
        }
        owner = _owner(manifest, relative)
        if owner:
            node["owner"] = owner
        _flag_format(scan, path, suffix, analysis)
        if analysis == "analyzed":
            _read_text(scan, path, source)


def _identify(scan: _Scan, path: str, uid: str, line: int) -> None:
    if _UID.fullmatch(uid):
        scan.uids[uid].add(path)
    else:
        scan.error("invalid_uid", path, "invalid authored resource UID: " + uid, line)


def _scan_external_resource(scan: _Scan, path: str, heading: Heading) -> None:
    attrs = heading.attrs
    target = attrs.get("path") or attrs.get("uid")
    if target:
        scan.reference(path, target, "resource", heading.line, attrs.get("uid"))
    else:
        scan.error(
            "missing_resource_identity",
            path,
            "external resource has neither path nor UID",
            heading.line,
        )


def _scan_scene(scan: _Scan, path: str, text: str) -> None:
    """Record the external resources of a scene or resource, and diagnose its local IDs."""
    ids: defaultdict[str, set[str]] = defaultdict(set)
    for heading in headings(text):
        section, attrs = heading.section, heading.attrs
        if section in {"ext_resource", "sub_resource"} and "id" in attrs:
            if attrs["id"] in ids[section]:
                scan.error(
                    "duplicate_local_id",
                    path,
                    "duplicate " + section + " ID: " + attrs["id"],
                    heading.line,
                )
            ids[section].add(attrs["id"])
        if section == "ext_resource":
            _scan_external_resource(scan, path, heading)


def _link_uid_sidecar(scan: _Scan, path: str) -> None:
    base = path[:-4]
    if base in scan.nodes:
        scan.reference(base, path, "uid_sidecar", origin="structural")
    else:
        scan.warn("orphan_uid", path, "UID sidecar has no declared source")


def _link_import_settings(scan: _Scan, path: str) -> None:
    base = path[:-7]
    if base in scan.nodes:
        scan.reference(base, path, "import_settings", origin="structural")


def _index_script(scan: _Scan, path: str, text: str) -> None:
    """Tokenize a script and index its global class name."""
    script = scan.scripts[path] = _code_tokens(text)
    for token, name in pairwise(script):
        if token[:2] == ("identifier", "class_name") and name[0] == "identifier":
            scan.classes[name[1]].add(path)


def _scan_declarations(scan: _Scan) -> None:
    """Collect the identities, local IDs, sidecar links and global classes the files declare."""
    for path, text in scan.texts.items():
        for owner, uid, line in file_identities(path, text, scan.nodes):
            _identify(scan, owner, uid, line)
        lower = path.lower()
        if lower.endswith((".tscn", ".tres")):
            _scan_scene(scan, path, text)
        elif lower.endswith(".uid"):
            _link_uid_sidecar(scan, path)
        elif lower.endswith(".import"):
            _link_import_settings(scan, path)
        elif lower.endswith(".gd"):
            _index_script(scan, path, text)


def _add_generated_uids(scan: _Scan, uids: dict[str, str]) -> None:
    """Identify the files without an authored UID by the UID the index records for them."""
    identified = {owner for owners in scan.uids.values() for owner in owners}
    for owner, uid in uids.items():
        node = "res://" + owner
        if node in scan.nodes and node not in identified:
            scan.uids[uid].add(node)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_metadata_index(scan: _Scan, manifest: dict) -> dict[str, set[str]]:
    """
    Add the UIDs that only generated sidecars declare to the identities.

    The project's metadata index also knows which references the build points at the UID of
    their path's file; returns those targets by source.
    """
    metadata = manifest.get("metadata_index")
    if not metadata:
        return {}
    index = _read_json(scan.execroot / metadata["path"])
    if not index:
        return {}
    _add_generated_uids(scan, index["uids"])
    # Unless resource UIDs are required, the build points these references
    # at the UID of their path's file.
    if not metadata["corrects"]:
        return {}
    return {
        "res://" + path: {"res://" + target for target in entry["uids"]}
        for path, entry in index["resource_uids"].items()
    }


def _assign_uids(scan: _Scan) -> None:
    """Record the UIDs on their nodes, and report each UID that several resources share."""
    for uid, paths in sorted(scan.uids.items()):
        for path in sorted(paths):
            scan.nodes[path]["uids"].append(uid)
        if len(paths) > 1:
            scan.error(
                "duplicate_uid",
                min(paths),
                uid + " belongs to multiple resources: " + ", ".join(sorted(paths)),
            )


def _diagnose_conflicting_uids(scan: _Scan) -> None:
    for path, node in sorted(scan.nodes.items()):
        if len(node["uids"]) > 1:
            scan.error(
                "conflicting_uids",
                path,
                "resource has multiple authored identities: " + ", ".join(node["uids"]),
            )


def _diagnose_duplicate_classes(scan: _Scan) -> None:
    for name, paths in sorted(scan.classes.items()):
        if len(paths) > 1:
            scan.error(
                "duplicate_class",
                min(paths),
                name + " belongs to multiple scripts: " + ", ".join(sorted(paths)),
            )


def _declare_runtime_references(scan: _Scan, manifest: dict) -> set[tuple[str, str]]:
    """Add the declared runtime references; returns their (source, target) pairs."""
    declared = set()
    for relation in manifest.get("relationships", []):
        if relation["kind"] != "runtime" or not relation["source"]:
            continue
        source = res_path(relation["source"])
        target = res_path(relation["target"])
        declared.add((source, target))
        scan.reference(source, target, "runtime", origin="declared")
        if source not in scan.nodes:
            scan.error(
                "missing_declared_source",
                source,
                "runtime declaration source is not in this project",
            )
    return declared


def _directories(nodes: Iterable[str]) -> set[str]:
    """Every directory below which the project declares a file."""
    directories = set()
    for path in nodes:
        parent = path.rpartition("/")[0]
        while parent != "res:/" and parent not in directories:
            directories.add(parent)
            parent = parent.rpartition("/")[0]
    return directories


_LOADERS = frozenset({"load", "preload", "load_threaded_request"})
_SHADER_FORMATS = (".gdshader", ".gdshaderinc", ".shader", ".shaderinc")


def _is_member_call(script: list, i: int) -> bool:
    """Whether the identifier at script[i] starts `Name.method(`."""
    return _at(script, i + 1)[1] == "." and _at(script, i + 3)[1] == "("


def _is_other_load(script: list, i: int) -> bool:
    """Whether a loader's name at script[i] declares a function or is another object's method."""
    before = _at(script, i - 1)[1]
    if before == "func":
        return True
    return before == "." and _at(script, i - 2)[1] != "ResourceLoader"


def _load_call(scan: _Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is a load call; if so, record its reference."""
    _, name, line = script[i]
    if name not in _LOADERS or _at(script, i + 1)[1] != "(":
        return False
    if _is_other_load(script, i):
        return True
    literal = _literal_argument(script, i + 1)
    if literal is None:
        scan.reference(path, None, "dynamic_load", line)
    else:
        kind = "preload" if name == "preload" else "load"
        scan.reference(path, literal, kind, line)
    return True


def _extends_clause(scan: _Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is `extends "path"`; if so, record its reference."""
    _, name, line = script[i]
    if name != "extends" or _at(script, i + 1)[0] != "string":
        return False
    scan.reference(path, script[i + 1][1], "script_extends", line)
    return True


def _class_use(scan: _Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] names a global class; if so, record a reference to its scripts."""
    _, name, line = script[i]
    if name not in scan.classes or _at(script, i - 1)[1] in {"class_name", "."}:
        return False
    # Conservative symbol index: shadowed identifiers can add edges. Full
    # GDScript name/type resolution belongs to Godot.
    for target in sorted(scan.classes[name]):
        if target != path:
            scan.reference(path, target, "script_class", line)
    return True


def _icon_annotation(scan: _Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is `@icon("path")`; if so, record its reference."""
    _, name, line = script[i]
    if name != "icon" or _at(script, i - 1)[1] != "@":
        return False
    icon = _literal_argument(script, i + 1, closers=(")",))
    if icon is None:
        return False
    scan.reference(path, icon, "script_icon", line)
    return True


def _names_resource(literal: str | None) -> bool:
    """Whether a path argument can name a project resource: user:// and file-system paths cannot."""
    return literal is None or literal.startswith("res://")


def _file_read_call(scan: _Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is a FileAccess call; if so, record the file it reads."""
    _, api, line = script[i]
    if api != "FileAccess" or not _is_member_call(script, i):
        return False
    literal = _literal_argument(script, i + 3)
    if _names_resource(literal) and script[i + 2][1] in _FILE_READS:
        kind = "file_access" if literal else "dynamic_file_access"
        scan.reference(path, literal, kind, line)
    return True


def _directory_listing_call(scan: _Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is a DirAccess call; if so, record the directory it lists."""
    _, api, line = script[i]
    if api != "DirAccess" or not _is_member_call(script, i):
        return False
    literal = _literal_argument(script, i + 3)
    if _names_resource(literal) and script[i + 2][1] in _DIRECTORY_LISTINGS:
        scan.reference(path, None, "directory_access", line)
    return True


# The first of these that recognizes an identifier records its reference.
_SCRIPT_REFERENCES = (
    _load_call,
    _extends_clause,
    _class_use,
    _icon_annotation,
    _file_read_call,
    _directory_listing_call,
)


def _scan_identifier(scan: _Scan, path: str, script: list, i: int) -> None:
    for recognize in _SCRIPT_REFERENCES:
        if recognize(scan, path, script, i):
            return


def _scan_script(scan: _Scan, path: str) -> None:
    """Record the references of a script's tokens, and where a string is unterminated."""
    script = scan.scripts[path]
    for i, (category, _, line) in enumerate(script):
        if category == "invalid":
            scan.error(
                "invalid_string",
                path,
                "unterminated string; analysis is incomplete",
                line,
            )
        elif category == "identifier":
            _scan_identifier(scan, path, script, i)


def _scan_shader(scan: _Scan, path: str, text: str) -> None:
    """Record the #include directives of a shader."""
    shader = _code_tokens(text, shader=True)
    for hash_, directive, argument in zip(shader, shader[1:], shader[2:]):
        if hash_[1] == "#" and directive[1] == "include":
            if argument[0] == "string":
                scan.reference(path, argument[1], "shader_include", hash_[2])
            else:
                scan.reference(path, None, "dynamic_include", hash_[2])


def _gltf_uris(model: dict) -> Iterator[tuple[str, object]]:
    for group in ("buffers", "images"):
        for entry in model.get(group, []):
            yield group, entry.get("uri")


def _gltf_reference(scan: _Scan, path: str, group: str, uri: object) -> None:
    if not isinstance(uri, str) or uri.startswith("data:"):
        return
    parsed = urlsplit(uri)
    if any((parsed.scheme, parsed.netloc, parsed.query, parsed.fragment)):
        scan.reference(path, None, "external_uri")
    else:
        scan.reference(path, unquote(parsed.path), "gltf_" + group)


def _scan_gltf(scan: _Scan, path: str, text: str) -> None:
    """Record the buffers and images a glTF model names by URI."""
    try:
        for group, uri in _gltf_uris(json.loads(text)):
            _gltf_reference(scan, path, group, uri)
    except (ValueError, TypeError, AttributeError) as error:
        scan.error("invalid_gltf", path, str(error))


def _entry_kind(section: str | None, key: str) -> str | None:
    """The kind of entry point a project setting names, if it is one."""
    if section == "autoload":
        return "autoload"
    return "main_scene" if (section, key) == ("application", "run/main_scene") else None


def _setting_values(statement: str) -> list[tuple[str, str, int]]:
    """The tokens a project setting assigns."""
    lexed = _code_tokens(statement)
    for i, token in enumerate(lexed):
        if token[1] == "=":
            return lexed[i + 1 :]
    return []


def _setting_references(
    section: str | None, key: str, statement: str
) -> list[tuple[str, str]]:
    """The (kind, reference) pairs of the resources a project setting names."""
    values = _setting_values(statement)
    entry = _entry_kind(section, key)
    if entry is None:
        # Settings such as the icon, theme or translations
        # name their resources by path or UID.
        return [
            ("project_setting", value)
            for category, value, _ in values
            if category == "string" and value.startswith(("res://", "uid://"))
        ]
    if values and values[0][0] == "string":
        return [(entry, values[0][1].lstrip("*"))]
    return []


def _scan_project(scan: _Scan, path: str, text: str) -> None:
    """Record the resources the project settings name; editor plugins never run when exported."""
    try:
        statements = statement_groups(text)
    except ValueError as error:
        scan.error("invalid_project", path, str(error))
        return
    line = 1
    for statement, section, key in statements:
        if key and section != "editor_plugins":
            for kind, reference in _setting_references(section, key, statement):
                scan.reference(path, reference, kind, line)
        line += statement.count("\n")


def _scan_references(scan: _Scan) -> None:
    """Record the references each analyzed file makes, as its format expresses them."""
    for path, text in scan.texts.items():
        lower = path.lower()
        if path in scan.scripts:
            _scan_script(scan, path)
        elif lower.endswith(_SHADER_FORMATS):
            _scan_shader(scan, path, text)
        elif lower.endswith(".gltf"):
            _scan_gltf(scan, path, text)
        elif path == _PROJECT_FILE:
            _scan_project(scan, path, text)


_IMPORT_KINDS = frozenset({"gltf_buffers", "gltf_images", "import_settings"})


def _dependency_kind(kind: str) -> str:
    """How an edge's source depends on its target: as an import input, as metadata or at runtime."""
    if kind in _IMPORT_KINDS:
        return "import"
    return "metadata" if kind == "uid_sidecar" else "runtime"


def _uid_of(edge: dict) -> str | None:
    """The UID an edge's reference names, or else carries beside its path."""
    reference = edge["reference"]
    return reference if reference.startswith("uid://") else edge["uid"]


def _candidate_path(edge: dict) -> str | None:
    """The path an edge's reference names, if it is not a UID; ValueError if it is invalid."""
    reference = edge["reference"]
    if reference.startswith("uid://"):
        return None
    # GDScript's parser resolves preload/extends against the script;
    # ResourceLoader and the global load() resolve relative to res://.
    base = _PROJECT_FILE if edge["kind"] == "load" else edge["source"]
    return res_path(reference, base)


def _below(nodes: Iterable[str], directory: str) -> list[str]:
    """The sorted nodes below a directory's res:// path."""
    prefix = directory + "/"
    return sorted(path for path in nodes if path.startswith(prefix))


class _Resolver:
    """Resolves the references of the scanned files to nodes, and diagnoses those that fail."""

    def __init__(
        self, scan: _Scan, declared: set[tuple[str, str]], corrected: dict[str, set[str]]
    ) -> None:
        self.scan = scan
        # The (source, target) pairs of the declared runtime references.
        self.declared = declared
        # The references the build points at the UID of their path's file, by source.
        self.corrected = corrected
        self.directories = _directories(scan.nodes)

    def resolve(self, edge: dict) -> None:
        """Set an edge's dependency kind, target and status."""
        edge["dependency_kind"] = _dependency_kind(edge["kind"])
        edge["target"], edge["target_kind"] = None, None
        status = self._find_target(edge)
        edge["status"] = self._check_available(edge) if status == "resolved" else status

    def _error(self, edge: dict, code: str, message: str) -> None:
        self.scan.error(code, edge["source"], message, edge["line"])

    def _warn(self, edge: dict, code: str, message: str) -> None:
        self.scan.warn(code, edge["source"], message, edge["line"])

    def _owners(self, edge: dict) -> set[str]:
        """The files that author the UID of an edge's reference."""
        uid = _uid_of(edge)
        return self.scan.uids.get(uid, set()) if uid else set()

    def _find_target(self, edge: dict) -> str:
        """Set the target of an edge; returns resolved or why there is none."""
        reference = edge["reference"]
        if reference is None:
            self._warn(
                edge,
                "dynamic_reference",
                "cannot statically determine "
                + edge["kind"]
                + "; declare runtime_references or runtime_deps",
            )
            return "unknown"
        try:
            candidate = _candidate_path(edge)
        except ValueError as error:
            self._error(edge, "invalid_reference", str(error) + ": " + reference)
            return "invalid"
        owners = self._owners(edge)
        if len(owners) > 1:
            self._error(
                edge,
                "ambiguous_uid_reference",
                f"UID has multiple owners: {_uid_of(edge)}",
            )
            return "ambiguous"
        if owners:
            edge["target"] = next(iter(owners))
            edge["target_kind"] = "uid" if candidate is None else "file"
            return self._settle_conflict(edge, candidate)
        return self._find_by_path(edge, candidate)

    def _settle_conflict(self, edge: dict, candidate: str | None) -> str:
        """Settle a reference whose UID and path identify different declared files."""
        if candidate not in self.scan.nodes or candidate == edge["target"]:
            return "resolved"
        fixed = candidate in self.corrected.get(edge["source"], set())
        (self._warn if fixed else self._error)(
            edge,
            "uid_path_conflict",
            f"{edge['reference']} and {_uid_of(edge)} identify different declared resources"
            + ("; the build uses the path's UID" if fixed else ""),
        )
        if not fixed:
            return "conflict"
        edge["target"], edge["target_kind"] = candidate, "file"
        return "resolved"

    def _find_by_path(self, edge: dict, candidate: str | None) -> str:
        if candidate in self.scan.nodes:
            edge["target"], edge["target_kind"] = candidate, "file"
            return "resolved"
        if candidate in self.directories:
            return self._find_directory(edge, candidate)
        self._error(
            edge,
            "missing_reference",
            "unavailable "
            + edge["kind"]
            + " reference: "
            + edge["reference"]
            + (
                " (no file has this UID)"
                if candidate is None
                else " (no declared file or directory)"
            ),
        )
        return "missing"

    def _find_directory(self, edge: dict, directory: str) -> str:
        if edge["kind"] not in DIRECTORY_REFERENCE_KINDS:
            self._error(
                edge,
                "invalid_reference",
                edge["kind"] + " reference names a directory: " + edge["reference"],
            )
            return "invalid"
        edge["target"], edge["target_kind"] = directory, "directory"
        edge["targets"] = _below(self.scan.nodes, directory)
        return "resolved"

    def _check_available(self, edge: dict) -> str:
        """Mark an edge declared or not, and diagnose a member's runtime use of an import input."""
        edge["declared"] = (edge["source"], edge["target"]) in self.declared
        if edge["source"] not in self.scan.nodes:
            return "invalid_source"
        if self._is_unavailable_at_runtime(edge):
            self._error(
                edge,
                "unavailable_runtime_reference",
                edge["target"]
                + (
                    " has only import inputs below it, no project member"
                    if edge["target_kind"] == "directory"
                    else " is an import input, not a project member"
                ),
            )
        return "resolved"

    def _is_unavailable_at_runtime(self, edge: dict) -> bool:
        """Whether a project member reaches no project member at runtime."""
        nodes = self.scan.nodes
        if (
            edge["dependency_kind"] != "runtime"
            or not nodes[edge["source"]]["membership"]
        ):
            return False
        return not any(nodes[path]["membership"] for path in _targets(edge))


def _unique_edges(edges: list[dict]) -> list[dict]:
    """The distinct edges in a stable order, which makes the graph useful to CI and authoring tools."""
    return sorted(
        {json.dumps(edge, sort_keys=True): edge for edge in edges}.values(),
        key=lambda edge: (
            edge["source"],
            edge["line"],
            edge["kind"],
            edge["reference"] or "",
            edge["origin"],
        ),
    )


def _coverage(nodes: dict[str, dict]) -> dict[str, list[str]]:
    """The paths of the nodes by how the scanner treats them."""
    return {
        classification: [
            path for path in sorted(nodes) if nodes[path]["analysis"] == classification
        ]
        for classification in ("analyzed", "leaf", "unsupported", "ignored")
    }


def _graph_document(manifest: dict, scan: _Scan, edges: list[dict]) -> dict:
    """The graph a scan of the manifest's files describes, with its diagnostics and coverage."""
    nodes = scan.nodes
    diagnostics = _sorted_diagnostics(scan.diagnostics)
    relationships = sorted(
        manifest.get("relationships", []),
        key=lambda item: (
            item["source"],
            item["target"],
            item["kind"],
            item.get("owner", ""),
        ),
    )
    coverage = _coverage(nodes)
    return {
        "schema_version": 2,
        "nodes": [nodes[path] for path in sorted(nodes)],
        "edges": edges,
        "relationships": relationships,
        "diagnostics": diagnostics,
        "coverage": coverage,
        "coverage_policy": {
            "analyzed_formats": sorted(ANALYZED_FORMATS),
            "leaf_formats": sorted(LEAF_FORMATS),
            "project_configuration": _PROJECT_FILE,
            "ignored": "files Godot never scans: hidden, or below a directory that holds a .gdignore or a project.godot",
            "custom_loaders_analyzed": False,
        },
        "complete": not coverage["unsupported"]
        and not any(edge["status"] != "resolved" for edge in edges)
        and not any(item["severity"] == "error" for item in diagnostics),
        "limits": [
            "static literals only; no program evaluation",
            "global class symbols are conservative",
            "unrecognized formats and custom loaders are not analyzed",
            "file-level reachability cannot prove non-use",
        ],
    }


def _is_inferred_runtime(edge: dict) -> bool:
    """Whether the scanner inferred a runtime reference, rather than the build or a declaration."""
    return edge["origin"] == "inferred" and edge["dependency_kind"] == "runtime"


def _is_undeclared(edge: dict) -> bool:
    """Whether a file's inferred runtime reference lacks a runtime_references entry."""
    if edge["status"] != "resolved" or edge["source"] == _PROJECT_FILE:
        return False
    return _is_inferred_runtime(edge) and not edge["declared"]


def _undeclared_references(edges: Iterable[dict]) -> list[dict]:
    """The errors for the inferred runtime references that no runtime_references entry declares."""
    return [
        diagnostic(
            "undeclared_reference",
            edge["source"],
            edge["kind"] + " requires runtime_references to " + edge["target"],
            edge["line"],
        )
        for edge in edges
        if _is_undeclared(edge)
    ]


def require_declared(graph: dict) -> dict:
    """
    Add an error for each inferred runtime reference without a matching runtime_references
    entry, and make each use of an add-on its resources do not declare one.

    References from the project configuration are implicit.
    """
    undeclared = _undeclared_references(graph["edges"])
    # A use of an add-on its resources do not declare is an error here too (FR-026).
    diagnostics = [
        dict(item, severity="error") if item["code"] == "undeclared_addon_use" else item
        for item in graph["diagnostics"]
    ]
    unused_addons = any(item["code"] == "undeclared_addon_use" for item in diagnostics)
    return dict(
        graph,
        diagnostics=_sorted_diagnostics(diagnostics + undeclared),
        complete=graph["complete"] and not undeclared and not unused_addons,
    )


def build_graph(manifest: dict, execroot: Path | None = None) -> dict:
    scan = _Scan(execroot or Path.cwd())
    sources, members = _declared_sources(manifest, scan)
    _declare_nodes(scan, manifest, sources, {res_path(path) for path in members})
    _scan_declarations(scan)
    corrected = _read_metadata_index(scan, manifest)
    _assign_uids(scan)
    _diagnose_conflicting_uids(scan)
    _diagnose_duplicate_classes(scan)
    _scan_references(scan)
    declared = _declare_runtime_references(scan, manifest)
    resolver = _Resolver(scan, declared, corrected)
    for edge in scan.edges:
        resolver.resolve(edge)
    edges = _unique_edges(scan.edges)
    _diagnose_undeclared_addon_uses(manifest, scan, edges)
    graph = _graph_document(manifest, scan, edges)
    return require_declared(graph) if manifest.get("require_declared") else graph


def _snapshot_uids(snapshot: dict | None) -> defaultdict[str, set[str]]:
    """The files of a graph snapshot by the UIDs they carry."""
    result = defaultdict(set)
    for node in snapshot["nodes"] if snapshot else ():
        for uid in node["uids"]:
            result[uid].add(node["path"])
    return result


def _merge_snapshots(graph: dict, previous: dict) -> dict:
    """The union of two snapshots of a graph, which retains removed and moved references."""
    return dict(
        graph,
        nodes=graph["nodes"] + previous["nodes"],
        edges=graph["edges"] + previous["edges"],
        complete=graph["complete"] and previous["complete"],
    )


def _query_roots(starts: Iterable[str]) -> list[str]:
    """The distinct roots of a query: UIDs as given, paths as res:// paths."""
    return sorted(
        {value if value.startswith("uid://") else res_path(value) for value in starts}
    )


def _root_files(
    value: str,
    current_uids: defaultdict[str, set[str]],
    previous_uids: defaultdict[str, set[str]],
    reverse: bool,
) -> set[str]:
    """The files a query root names; none if it names no file, or by UID several."""
    if not value.startswith("uid://"):
        return {value}
    current, old = current_uids[value], previous_uids[value]
    # A moved UID may have one distinct owner per snapshot. Preserve
    # both affected roots, but prefer its present location for ordinary
    # reachability. Duplicate ownership within a snapshot is ambiguous.
    if len(current) > 1:
        return set()
    searches_old = reverse or not current
    if searches_old and len(old) > 1:
        return set()
    return current | old if reverse else current or old


def _file_pairs(edges: Iterable[dict]) -> Iterator[tuple[str, str]]:
    """The (source, target) files of each resolved edge."""
    for edge in edges:
        if edge["status"] == "resolved":
            for target in _targets(edge):
                yield edge["source"], target


def _adjacency(edges: Iterable[dict], reverse: bool) -> defaultdict[str, set[str]]:
    """The files each file reaches through its resolved edges, or is reached from if reversed."""
    adjacency = defaultdict(set)
    for source, target in _file_pairs(edges):
        start, end = (target, source) if reverse else (source, target)
        adjacency[start].add(end)
    return adjacency


def _parents(
    roots: set[str],
    known: set[str],
    adjacency: defaultdict[str, set[str]],
    reverse: bool,
) -> dict[str, str | None]:
    """The file each reached file was first reached from, breadth first; roots have none."""
    parents = {value: None for value in sorted(roots)}
    if reverse and _PROJECT_FILE in roots:
        # Project settings can influence every import and script. Static source
        # references alone do not describe that configuration dependency.
        parents.update(
            {value: _PROJECT_FILE for value in sorted(known) if value not in parents}
        )
    queue = deque(sorted(roots))
    while queue:
        source = queue.popleft()
        for target in sorted(adjacency[source]):
            if target not in parents:
                parents[target] = source
                queue.append(target)
    return parents


def query_graph(
    graph: dict,
    starts: list[str],
    *,
    reverse: bool = False,
    previous: dict | None = None,
) -> dict:
    """Return file-level transitive reachability and shortest explanation chains."""
    current_uids, previous_uids = _snapshot_uids(graph), _snapshot_uids(previous)
    if previous is not None:
        graph = _merge_snapshots(graph, previous)
    known = {node["path"] for node in graph["nodes"]}
    resolved = set()
    for value in _query_roots(starts):
        candidates = _root_files(value, current_uids, previous_uids, reverse)
        if not candidates or not candidates <= known:
            raise ValueError("query root is missing or ambiguous: " + value)
        resolved.update(candidates)
    parents = _parents(resolved, known, _adjacency(graph["edges"], reverse), reverse)
    return {
        "direction": "affected" if reverse else "reachable",
        "roots": sorted(resolved),
        "paths": sorted(parents),
        "chains": {path: _chain(parents, path) for path in sorted(parents)},
        "conservative": True,
        "complete": graph["complete"],
    }


class SelectionError(ValueError):
    """A pack whose references are unavailable or not fully declared."""

    def __init__(self, diagnostics: list[dict]) -> None:
        super().__init__("\n".join(format_diagnostic(item) for item in diagnostics))
        self.diagnostics = diagnostics


def _hiding_cause(hider: str) -> str:
    """Why the export leaves out a file: its directory holds a marker, or is itself hidden."""
    cause = (
        "hides its directory"
        if PurePosixPath(hider).name in DIRECTORY_MARKERS
        else "is a hidden directory"
    )
    return f"res://{hider} {cause}"


def _hidden_files(nodes: dict[str, dict]) -> dict[str, str]:
    """
    Why the export leaves out each Godot-ignored file it leaves out.

    Godot still packs a hidden file of a visible directory.
    """
    ignored = [path for path, node in nodes.items() if node["analysis"] == "ignored"]
    paths = {path.removeprefix("res://") for path in nodes} if ignored else set()
    hiders = {path: hidden_by(path.removeprefix("res://"), paths) for path in ignored}
    return {path: _hiding_cause(hider) for path, hider in hiders.items() if hider}


def _outgoing_edges(edges: Iterable[dict]) -> defaultdict[str, list[dict]]:
    outgoing = defaultdict(list)
    for edge in edges:
        outgoing[edge["source"]].append(edge)
    return outgoing


def _acknowledged_reads(
    edges: Iterable[dict], hidden: dict[str, str]
) -> set[tuple[str, str]]:
    """The (source, target) pairs of declared references to files the export leaves out."""
    return {(s, t) for s, t in _file_pairs(edges) if t in hidden}


def _group_relationships(
    relationships: Iterable[dict],
) -> tuple[defaultdict[str, set[str]], defaultdict[str, set[str]]]:
    """
    Group the relationships without a source.

    Returns the targets declaring each file, and the members of each target's runtime_deps.
    """
    owners, groups = defaultdict(set), defaultdict(set)
    for relation in relationships:
        if not relation["source"]:
            target = res_path(relation["target"])
            if relation["kind"] == "membership":
                owners[target].add(relation["owner"])
            elif relation["kind"] == "runtime":
                groups[relation["owner"]].add(target)
    return owners, groups


def _required_files(required: Iterable[dict]) -> Iterator[tuple[str, str, str]]:
    """The (pack, path, source file) of each resource the required packs provide."""
    for content in required:
        for path, source in content["resources"].items():
            yield content["pack"], res_path(path), source


class _PackSelection(_Findings):
    """Selects a pack's resources by following the references of a resource graph from roots."""

    def __init__(
        self, graph: dict, reachable: bool, excluded: set[str], libraries: set[str]
    ) -> None:
        super().__init__()
        self.reachable = reachable
        self.excluded = excluded
        # Application rules deliver the extension libraries.
        self.libraries = libraries
        self.graph_diagnostics = graph["diagnostics"]
        self.nodes = {node["path"]: node for node in graph["nodes"]}
        self.members = {path for path, node in self.nodes.items() if node["membership"]}
        # Why the export leaves out each Godot-ignored file it leaves out.
        self.hidden = _hidden_files(self.nodes)
        self.outgoing = _outgoing_edges(graph["edges"])
        declarations = [edge for edge in graph["edges"] if edge["origin"] == "declared"]
        # The files with a declared reference, and the reads of hidden files among them.
        self.declared = {edge["source"] for edge in declarations}
        self.acknowledged = _acknowledged_reads(declarations, self.hidden)
        self.owners, self.groups = _group_relationships(graph["relationships"])
        # The required pack that provides each path.
        self.provided: dict[str, str] = {}
        self.parents: dict[str, str | None] = {}
        self.reached_provided: set[str] = set()
        self.expanded_groups: set[str] = set()
        self.queue: deque[str] = deque()

    def provide(self, required: Iterable[dict], sources: dict | None) -> None:
        """
        Record the content of the required packs.

        A path has one file across this project and its required packs.
        """
        origins = {
            path: ("this project", source) for path, source in (sources or {}).items()
        }
        for pack, path, source in _required_files(required):
            origin, previous = origins.setdefault(path, (pack, source))
            if previous != source:
                self.error(
                    "identity_conflict",
                    path,
                    f"{origin} uses {previous}, {pack} provides {source}",
                )
            self.provided.setdefault(path, pack)

    def select(self, entry_points: Iterable[str], extensions: Iterable[str]) -> dict:
        """Reach the files the pack contains; raises SelectionError for any violation."""
        # The project configuration is a root that the pack never contains.
        if _PROJECT_FILE in self.nodes:
            self._reach(_PROJECT_FILE, None, "project")
        roots = (
            self._reachable_roots(entry_points, extensions)
            if self.reachable
            else self._member_roots()
        )
        for path, kind in roots:
            self._reach(path, None, kind)
        while self.queue:
            self._expand(self.queue.popleft())
        diagnostics = self._diagnostics()
        if any(item["severity"] == "error" for item in diagnostics):
            raise SelectionError(diagnostics)
        return self._report(diagnostics)

    def _member_roots(self) -> Iterator[tuple[str, str]]:
        """The (path, kind of reference) of every file the pack may contain."""
        members = sorted(self.members - self.excluded - self.libraries)
        return ((path, "member") for path in members)

    def _reachable_roots(
        self, entry_points: Iterable[str], extensions: Iterable[str]
    ) -> Iterator[tuple[str, str]]:
        """The (path, kind of reference) of the entry points, extensions and unowned runtime_deps."""
        for path in entry_points:
            yield path, "entry_point"
        for path in extensions:
            yield path, "extension"
        # Without files of its own, nothing shows when such a target is used.
        for owner in sorted(self.groups.keys() - set().union(*self.owners.values())):
            yield from ((path, "runtime_deps") for path in sorted(self.groups[owner]))

    def _report(self, diagnostics: list[dict]) -> dict:
        resources = sorted(self.parents.keys() - {_PROJECT_FILE})
        return {
            "diagnostics": diagnostics,
            "mode": "reachable" if self.reachable else "members",
            "resources": resources,
            "chains": {path: _chain(self.parents, path) for path in resources}
            if self.reachable
            else {},
            "required": {
                path: self.provided[path] for path in sorted(self.reached_provided)
            },
        }

    def _diagnostics(self) -> list[dict]:
        """The distinct findings, in order; reachable selection also fails on reached graph errors."""
        if self.reachable:
            # What reachable selection packs depends on the graph being sound.
            self.diagnostics.extend(
                item
                for item in self.graph_diagnostics
                if item["severity"] == "error" and item["path"] in self.parents
            )
        unique = {
            (item["path"], item["line"], item["code"], item["message"]): item
            for item in self.diagnostics
        }
        return _sorted_diagnostics(list(unique.values()))

    def _covered(self, path: str) -> bool:
        """Whether declarations name what a file uses beyond the scanner's view."""
        return path in self.declared or any(
            self.groups[owner] for owner in self.owners[path]
        )

    def _reach(self, path: str, parent: str | None, kind: str) -> None:
        if path in self.provided:
            self.reached_provided.add(path)
        elif path in self.libraries or path not in self.members:
            # Runtime uses of import inputs are already graph diagnostics.
            return
        elif path in self.excluded:
            if kind not in SOFT_REFERENCE_KINDS:
                self.error(
                    "unavailable_reference",
                    parent or path,
                    f"{kind} reference to excluded {path}",
                )
        elif path not in self.parents:
            self.parents[path] = parent
            self.queue.append(path)

    def _leaves_out(self, edge: dict) -> None:
        """Report a reference from a packed file to a file Godot's export leaves out."""
        cause = self.hidden.get(edge["target"])
        if cause is None or not _is_inferred_runtime(edge):
            return
        # Code may read a file only when it runs from the sources.
        read = edge["kind"] == "file_access"
        if read and (edge["source"], edge["target"]) in self.acknowledged:
            return
        hint = (
            "; a runtime_references entry from this file acknowledges a read that runs only from the sources"
            if read
            else ""
        )
        (self.warn if read else self.error)(
            "ignored_reference",
            edge["source"],
            f"{edge['kind']} reference to {edge['target']}, which Godot's export leaves out: {cause}{hint}",
            edge["line"],
        )

    def _follow(self, edge: dict, path: str) -> None:
        if edge["status"] == "resolved":
            self._leaves_out(edge)
            for target in _targets(edge):
                self._reach(target, path, edge["kind"])
        elif edge["status"] == "unknown" and self._needs_declaration(path):
            self.error(
                "undeclared_dynamic_reference",
                path,
                f"{edge['kind']} on line {edge['line']} may use unselected files; declare runtime_references from this file or runtime_deps on its target",
            )

    def _needs_declaration(self, path: str) -> bool:
        """Whether a file's unknown references must be declared: reachable selection packs only what is reached."""
        return self.reachable and not self._covered(path)

    def _expand(self, path: str) -> None:
        for edge in self.outgoing[path]:
            self._follow(edge, path)
        for owner in sorted(self.owners[path] - self.expanded_groups):
            self.expanded_groups.add(owner)
            for target in sorted(self.groups[owner]):
                self._reach(target, path, "runtime_deps")


def select_pack(
    graph: dict,
    *,
    reachable: bool,
    entry_points: Iterable[str] = (),
    extensions: Iterable[str] = (),
    excluded: Iterable[str] = (),
    extension_library_paths: Iterable[str] = (),
    required: Iterable[dict] = (),
    sources: dict | None = None,
) -> dict:
    """
    Select a pack's own resources and check that what they reference is available.

    Paths are res:// identities; sources maps this project's members to their
    files. required lists the content of required packs, {"pack", "resources"}
    with resource paths to files. A path has one file across
    this project and its required packs. Excluded, extension library and required
    paths are never packed. A hard reference must end in this pack or a
    required pack. Reachable selection starts from the project
    configuration, entry points and extension descriptors, and fails where a
    reached file may load undeclared files or has graph errors. A reference to a
    file Godot's export leaves out is an error, a file read a warning unless a
    declared runtime reference from the reading file names the file. Raises
    SelectionError listing every violation; the report lists the warnings.
    """
    selection = _PackSelection(
        graph, reachable, set(excluded), set(extension_library_paths)
    )
    selection.provide(required, sources)
    return selection.select(entry_points, extensions)


def select_from_manifest(
    manifest: dict, graph: dict, project: dict, execroot: Path
) -> tuple[dict, dict]:
    """
    Return a pack's selection report and the content it provides to dependent packs.

    graph is the project's resource graph and project the manifest it scanned.
    """

    def paths(key: str) -> list[str]:
        return [res_path(path) for path in manifest[key]]

    entry_points = paths("entry_points")
    sources = {
        res_path(path): source
        for path, source in project["member_resource_paths"].items()
    }
    required = [_read_json(execroot / content) for content in manifest["required"]]
    selection = select_pack(
        graph,
        reachable=manifest["selection"] == "reachable",
        entry_points=entry_points,
        extensions=paths("extensions"),
        excluded=paths("excluded"),
        extension_library_paths=paths("extension_library_paths"),
        required=required,
        sources=sources,
    )
    resources = {
        path.removeprefix("res://"): sources[path] for path in selection["resources"]
    }
    return dict(selection, pack=manifest["pack"], entry_points=entry_points), {
        "pack": manifest["pack"],
        "resources": resources,
    }


def _run_scan(args: argparse.Namespace) -> int:
    manifest = read_manifest(args.manifest)
    if args.addons:
        uses = read_manifest(args.addons)
        manifest.update(addons=uses["addons"], addon_uses=uses["addon_uses"])
    graph = build_graph(manifest, args.execroot)
    if args.output:
        args.output.write_text(_json(graph), encoding="utf-8")
    else:
        print(_json(graph), end="")
    return 0


def _scan_command(commands: Any) -> None:
    scan = commands.add_parser(
        "scan", help="analyze only files explicitly listed in a JSON-lines manifest"
    )
    scan.add_argument("--manifest", type=Path, required=True)
    scan.add_argument("--output", type=Path)
    scan.add_argument("--execroot", type=Path, default=Path.cwd())
    scan.add_argument(
        "--addons",
        type=Path,
        help="JSON-lines file of the operation's add-ons and each unit's uses",
    )
    scan.set_defaults(run=_run_scan)


def _run_check(args: argparse.Namespace) -> int:
    graph = _read_json(args.graph)
    if args.require_declared:
        graph = require_declared(graph)
    args.output.write_text(_json(graph), encoding="utf-8")
    if not args.validate:
        return 0
    for item in graph["diagnostics"]:
        print(format_diagnostic(item), file=sys.stderr)
    return int(any(item["severity"] == "error" for item in graph["diagnostics"]))


def _check_command(commands: Any) -> None:
    check = commands.add_parser(
        "check", help="write a scanned graph with optional stricter diagnostics"
    )
    check.add_argument("--graph", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    check.add_argument(
        "--validate",
        action="store_true",
        help="fail on error diagnostics after writing the graph",
    )
    check.add_argument("--require-declared", action="store_true")
    check.set_defaults(run=_run_check)


def _run_query(args: argparse.Namespace) -> int:
    graph = _read_json(args.graph)
    previous = _read_json(args.previous_graph) if args.previous_graph else None
    result = query_graph(
        graph, args.paths, reverse=args.direction == "affected", previous=previous
    )
    print(_json(result), end="")
    return 0


def _query_command(commands: Any) -> None:
    query = commands.add_parser("query", help="query a previously generated graph")
    query.add_argument("--graph", type=Path, required=True)
    query.add_argument(
        "--direction", choices=["reachable", "affected"], default="reachable"
    )
    query.add_argument(
        "--previous-graph",
        type=Path,
        help="union old/new dependencies to retain removed and moved references",
    )
    query.add_argument("paths", nargs="+")
    query.set_defaults(run=_run_query)


def _run_select(args: argparse.Namespace) -> int:
    selection, content = select_from_manifest(
        _read_json(args.manifest),
        _read_json(args.graph),
        read_manifest(args.project_manifest),
        args.execroot,
    )
    args.output.write_text(_json(selection), encoding="utf-8")
    args.content.write_text(_json(content), encoding="utf-8")
    for item in selection["diagnostics"]:
        print(format_diagnostic(item), file=sys.stderr)
    return 0


def _select_command(commands: Any) -> None:
    select = commands.add_parser(
        "select", help="select a pack's resources and check their availability"
    )
    select.add_argument(
        "--manifest", type=Path, required=True, help="the pack's selection manifest"
    )
    select.add_argument(
        "--graph", type=Path, required=True, help="the project's resource graph"
    )
    select.add_argument(
        "--project-manifest",
        type=Path,
        required=True,
        help="the manifest the project's graph was scanned from",
    )
    select.add_argument(
        "--output",
        type=Path,
        required=True,
        help="selection report with explanation chains",
    )
    select.add_argument(
        "--content",
        type=Path,
        required=True,
        help="resources this pack provides to dependent packs",
    )
    select.add_argument("--execroot", type=Path, default=Path.cwd())
    select.set_defaults(run=_run_select)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for add_command in (_scan_command, _check_command, _query_command, _select_command):
        add_command(commands)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
