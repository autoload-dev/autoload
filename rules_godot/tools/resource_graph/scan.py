"""
The scanner of the resource graph: finds what Godot files declare and reference, without
running Godot.

Each reference becomes an edge from its file, and graph.py resolves the edges between a
project's declared files. Gazelle's Godot language reads single files with
file_references. The lexer, section headings and identities are in resources/text.py.

Sections: Script tokens, Scan, Reference scanning, Reference targets, Single files.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Container, Iterator, Mapping
from itertools import pairwise
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tools.project.statements import statement_groups
from tools.resource_graph.diagnostics import Findings
from tools.resources.text import (
    PROJECT_FILE,
    UID,
    Heading,
    file_identities,
    headings,
    res_path,
    tokens,
)

# ==== Script tokens ===========================================================


def _code_tokens(text: str, *, shader: bool = False) -> list[tuple[str, str, int]]:
    """The tokens of the text, newlines removed."""
    return [token for token in tokens(text, shader=shader) if token[0] != "newline"]


_NO_TOKEN = ("", "", 0)


def _at(script: list, i: int) -> tuple[str, str, int]:
    """The token at script[i], or an empty one outside the script."""
    return script[i] if 0 <= i < len(script) else _NO_TOKEN


def _literal_argument(
    script: list,
    paren: int,
    closers: Container[str] = (")", ","),
    constants: Mapping[str, str] | None = None,
) -> str | None:
    """
    The first argument of the call opened at script[paren], if it is a lone string literal or
    a constant of the script whose value is one.
    """
    if _at(script, paren)[1] != "(":
        return None
    argument, closer = _at(script, paren + 1), _at(script, paren + 2)
    if closer[1] not in closers:
        return None
    if argument[0] == "identifier":
        return (constants or {}).get(argument[1])
    return argument[1] if argument[0] == "string" else None


def _literal_value(script: list, assign: int) -> str | None:
    """The value assigned at script[assign] if it is a lone string literal, which ends its line."""
    value, after = _at(script, assign + 1), _at(script, assign + 2)
    if value[0] != "string":
        return None
    # The statement ends after the literal: at the end of its line or at a semicolon.
    ends = after[2] != value[2] or after[1] in ("", ";")
    return value[1] if ends else None


def _literal_constant(script: list, i: int) -> tuple[str, str] | None:
    """The name and value of a constant declared at script[i] whose value is a literal."""
    name = _at(script, i + 1)
    if script[i][1] != "const" or name[0] != "identifier":
        return None
    assign = next((j for j in range(i + 2, i + 5) if _at(script, j)[1] == "="), None)
    value = None if assign is None else _literal_value(script, assign)
    return None if value is None else (name[1], value)


def _literal_constants(script: list) -> dict[str, str]:
    """
    The script's constants whose whole value is a string literal, by name. A name the script
    declares more than once, such as in an inner class, names nothing certain and is left out.
    """
    declared = Counter(
        name[1]
        for keyword, name in pairwise(script)
        if keyword[1] in ("const", "var") and name[0] == "identifier"
    )
    found = (_literal_constant(script, i) for i in range(len(script)))
    return {name: value for name, value in filter(None, found) if declared[name] == 1}


# ==== Scan ====================================================================


class Scan(Findings):
    """What the scanner collects from a project's files, or from a single file."""

    def __init__(self, execroot: Path) -> None:
        super().__init__()
        self.execroot = execroot
        self.nodes: dict[str, dict] = {}
        self.texts: dict[str, str] = {}
        self.scripts: dict[str, list[tuple[str, str, int]]] = {}
        self.constants: dict[str, dict[str, str]] = {}
        self.uids: defaultdict[str, set[str]] = defaultdict(set)
        self.classes: defaultdict[str, set[str]] = defaultdict(set)
        self.edges: list[dict] = []

    def reference(
        self, source: str, target: str | None, kind: str, line: int = 0
    ) -> dict:
        """Records a reference that the scanner found in a file and returns its edge."""
        edge = {
            "source": source,
            "reference": target,
            "kind": kind,
            "line": line,
            "uid": None,
            "origin": "inferred",
        }
        self.edges.append(edge)
        return edge

    def link(self, source: str, target: str, kind: str, origin: str) -> None:
        """Records an edge that the project's structure or a declaration makes, not a file's text."""
        self.reference(source, target, kind)["origin"] = origin


def _identify(scan: Scan, path: str, uid: str, line: int) -> None:
    if UID.fullmatch(uid):
        scan.uids[uid].add(path)
    else:
        scan.error("invalid_uid", path, "invalid authored resource UID: " + uid, line)


def _scan_external_resource(scan: Scan, path: str, heading: Heading) -> None:
    attrs = heading.attrs
    target = attrs.get("path") or attrs.get("uid")
    if target:
        edge = scan.reference(path, target, "resource", heading.line)
        # An external resource carries its UID beside its path.
        edge["uid"] = attrs.get("uid")
    else:
        scan.error(
            "missing_resource_identity",
            path,
            "external resource has neither path nor UID",
            heading.line,
        )


def _scan_scene(scan: Scan, path: str, text: str) -> None:
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


def _link_uid_sidecar(scan: Scan, path: str) -> None:
    base = path[:-4]
    if base in scan.nodes:
        scan.link(base, path, "uid_sidecar", "structural")
    else:
        scan.warn("orphan_uid", path, "UID sidecar has no declared source")


def _link_import_settings(scan: Scan, path: str) -> None:
    base = path[:-7]
    if base in scan.nodes:
        scan.link(base, path, "import_settings", "structural")


def _index_script(scan: Scan, path: str, text: str) -> None:
    """Tokenize a script and index its global class name."""
    script = scan.scripts[path] = _code_tokens(text)
    scan.constants[path] = _literal_constants(script)
    for token, name in pairwise(script):
        if token[:2] == ("identifier", "class_name") and name[0] == "identifier":
            scan.classes[name[1]].add(path)


def scan_declarations(scan: Scan) -> None:
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


# ==== Reference scanning ======================================================


_LOADERS = frozenset({"load", "preload", "load_threaded_request"})

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


def _is_member_call(script: list, i: int) -> bool:
    """Whether the identifier at script[i] starts `Name.method(`."""
    return _at(script, i + 1)[1] == "." and _at(script, i + 3)[1] == "("


def _is_other_load(script: list, i: int) -> bool:
    """
    Whether the loader name at script[i] is no load call.

    It is none when it declares a function or calls another object's method.
    """
    before = _at(script, i - 1)[1]
    if before == "func":
        return True
    return before == "." and _at(script, i - 2)[1] != "ResourceLoader"


def _load_call(scan: Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is a load call; if so, record its reference."""
    _, name, line = script[i]
    if name not in _LOADERS or _at(script, i + 1)[1] != "(":
        return False
    if _is_other_load(script, i):
        return True
    literal = _literal_argument(script, i + 1, constants=scan.constants.get(path))
    if literal is None:
        scan.reference(path, None, "dynamic_load", line)
    else:
        kind = "preload" if name == "preload" else "load"
        scan.reference(path, literal, kind, line)
    return True


def _extends_clause(scan: Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is `extends "path"`; if so, record its reference."""
    _, name, line = script[i]
    if name != "extends" or _at(script, i + 1)[0] != "string":
        return False
    scan.reference(path, script[i + 1][1], "script_extends", line)
    return True


def _may_name_class(script: list, i: int) -> bool:
    """Whether the identifier at script[i] stands where it may name a global class."""
    return _at(script, i - 1)[1] not in {"class_name", "."}


def _class_use(scan: Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] names a global class; if so, record a reference to its scripts."""
    _, name, line = script[i]
    if name not in scan.classes or not _may_name_class(script, i):
        return False
    # This index over-reports. A shadowed identifier can add an edge that does not
    # exist. Only Godot resolves GDScript names and types fully.
    for target in sorted(scan.classes[name]):
        if target != path:
            scan.reference(path, target, "script_class", line)
    return True


def _icon_annotation(scan: Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is `@icon("path")`; if so, record its reference."""
    _, name, line = script[i]
    if name != "icon" or _at(script, i - 1)[1] != "@":
        return False
    icon = _literal_argument(
        script, i + 1, closers=(")",), constants=scan.constants.get(path)
    )
    if icon is None:
        return False
    scan.reference(path, icon, "script_icon", line)
    return True


def _names_resource(literal: str | None) -> bool:
    """Whether a path argument can name a project resource: user:// and file-system paths cannot."""
    return literal is None or literal.startswith("res://")


def _file_read_call(scan: Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is a FileAccess call; if so, record the file it reads."""
    _, api, line = script[i]
    if api != "FileAccess" or not _is_member_call(script, i):
        return False
    literal = _literal_argument(script, i + 3, constants=scan.constants.get(path))
    if _names_resource(literal) and script[i + 2][1] in _FILE_READS:
        kind = "file_access" if literal else "dynamic_file_access"
        scan.reference(path, literal, kind, line)
    return True


def _directory_listing_call(scan: Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is a DirAccess call; if so, record the directory it lists."""
    _, api, line = script[i]
    if api != "DirAccess" or not _is_member_call(script, i):
        return False
    literal = _literal_argument(script, i + 3, constants=scan.constants.get(path))
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


def _scan_identifier(scan: Scan, path: str, script: list, i: int) -> None:
    for recognize in _SCRIPT_REFERENCES:
        if recognize(scan, path, script, i):
            return


def _scan_script(scan: Scan, path: str) -> None:
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


_SHADER_FORMATS = (".gdshader", ".gdshaderinc", ".shader", ".shaderinc")


def _scan_shader(scan: Scan, path: str, text: str) -> None:
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


def _gltf_reference(scan: Scan, path: str, group: str, uri: object) -> None:
    if not isinstance(uri, str) or uri.startswith("data:"):
        return
    parsed = urlsplit(uri)
    if any((parsed.scheme, parsed.netloc, parsed.query, parsed.fragment)):
        scan.reference(path, None, "external_uri")
    else:
        scan.reference(path, unquote(parsed.path), "gltf_" + group)


def _scan_gltf(scan: Scan, path: str, text: str) -> None:
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


def _scan_project(scan: Scan, path: str, text: str) -> None:
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


def scan_references(scan: Scan) -> None:
    """Record the references each analyzed file makes, as its format expresses them."""
    for path, text in scan.texts.items():
        lower = path.lower()
        if path in scan.scripts:
            _scan_script(scan, path)
        elif lower.endswith(_SHADER_FORMATS):
            _scan_shader(scan, path, text)
        elif lower.endswith(".gltf"):
            _scan_gltf(scan, path, text)
        elif path == PROJECT_FILE:
            _scan_project(scan, path, text)


# ==== Reference targets =======================================================


def uid_of(edge: dict) -> str | None:
    """The edge's UID: its reference if that is a UID, else the UID beside its path."""
    reference = edge["reference"]
    return reference if reference.startswith("uid://") else edge["uid"]


def candidate_path(edge: dict) -> str | None:
    """The path an edge's reference names, if it is not a UID; ValueError if it is invalid."""
    reference = edge["reference"]
    if reference.startswith("uid://"):
        return None
    # GDScript's parser resolves preload/extends against the script;
    # ResourceLoader and the global load() resolve relative to res://.
    base = PROJECT_FILE if edge["kind"] == "load" else edge["source"]
    return res_path(reference, base)


# ==== Single files ============================================================


class _AnySource:
    """
    A set of declared sources that holds every path.

    A single file has no project that says which sources exist, so every sidecar authors
    the identity of its source.
    """

    def __contains__(self, item: object) -> bool:
        return True


def _extended_class(script: list) -> str | None:
    """The global class the script itself extends by name, not one of its inner classes."""
    for i, (_, value, _) in enumerate(script):
        if value == "extends" and _at(script, i - 2)[1] != "class":
            base = _at(script, i + 1)
            return base[1] if base[0] == "identifier" else None
    return None


def _file_reference(edge: dict) -> dict | None:
    """An edge with its path normalized as the graph resolves it; None for an unknown one."""
    if edge["reference"] is None:
        return None
    try:
        path = candidate_path(edge)
    except ValueError:
        path = None
    return {"kind": edge["kind"], "path": path, "uid": uid_of(edge)}


def file_references(path: str, text: str) -> dict:
    """
    What one file at a res:// path declares and references on its own, without its project.

    The result holds the UIDs the file authors, a sidecar's for its file; the global classes
    a script declares, the one it extends by name and every name it may use as a global
    class; and the references the graph records, each with its kind, its normalized path and
    its UID. Gazelle's Godot language derives dependencies from it.
    """
    scan = Scan(Path.cwd())
    scan.nodes[path] = {"path": path}
    scan.texts[path] = text
    scan_declarations(scan)
    scan_references(scan)
    script = scan.scripts.get(path, [])
    names = {
        name
        for i, (category, name, _) in enumerate(script)
        if category == "identifier" and _may_name_class(script, i)
    }
    references = (_file_reference(edge) for edge in scan.edges)
    return {
        "uids": [uid for _, uid, _ in file_identities(path, text, _AnySource())],
        "classes": sorted(scan.classes),
        "extends": _extended_class(script),
        "names": sorted(names - set(scan.classes)),
        "references": sorted(
            (item for item in references if item),
            key=lambda item: (item["kind"], item["path"] or "", item["uid"] or ""),
        ),
    }
