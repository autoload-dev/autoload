"""
Bounded static Godot reference analysis; never discovers Bazel action inputs.

Graph paths are res:// identities, not execroot paths. The scanner deliberately
does not execute Godot, scripts, importers, or addon code. Unknown dynamic loads
remain diagnostics and must be covered by explicit declarations.

The lexer, section headings and identities it builds on are in resources/text.py, and
pack_selection.py selects a pack's resources from the graph.

The command line (command.py) scans and checks graphs and queries them
(query.py).

Sections: Diagnostics, Script tokens, Scan, Reference scanning, Graph, Single files.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Container, Iterable, Iterator, Mapping
from itertools import pairwise
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from tools.project.statements import statement_groups
from tools.resources.text import (
    ANALYZED_FORMATS,
    LEAF_FORMATS,
    PROJECT_FILE,
    UID,
    Heading,
    file_identities,
    headings,
    portable_identity,
    res_path,
    tokens,
)

# ==== Diagnostics =============================================================


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


def sorted_diagnostics(diagnostics: list[dict]) -> list[dict]:
    return sorted(
        diagnostics,
        key=lambda item: (item["path"], item["line"], item["code"], item["message"]),
    )


class Findings:
    """Collects the findings of a pass over the files of a project."""

    def __init__(self) -> None:
        self.diagnostics: list[dict] = []

    def error(self, code: str, path: str, message: str, line: int = 0) -> None:
        self.diagnostics.append(diagnostic(code, path, message, line))

    def warn(self, code: str, path: str, message: str, line: int = 0) -> None:
        self.diagnostics.append(warning(code, path, message, line))


# ==== Script tokens ===========================================================


def _code_tokens(text: str, *, shader: bool = False) -> list[tuple[str, str, int]]:
    """The tokens of lex without its newlines."""
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


class _Scan(Findings):
    """What build_graph collects from the declared files of a project."""

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
                PROJECT_FILE,
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
    if suffix in ANALYZED_FORMATS or path == PROJECT_FILE:
        return "analyzed"
    return "leaf" if suffix in LEAF_FORMATS else "unsupported"


# Built-in loaders of these unanalyzed formats resolve further resources; the
# graph records that as a reference it cannot determine.
UNANALYZED_CONTAINERS = frozenset({".res", ".scn"})


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
    if UID.fullmatch(uid):
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
    scan.constants[path] = _literal_constants(script)
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


def read_json(path: Path) -> dict:
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
    index = read_json(scan.execroot / metadata["path"])
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
    literal = _literal_argument(script, i + 1, constants=scan.constants.get(path))
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


def _may_name_class(script: list, i: int) -> bool:
    """Whether the identifier at script[i] stands where it may name a global class."""
    return _at(script, i - 1)[1] not in {"class_name", "."}


def _class_use(scan: _Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] names a global class; if so, record a reference to its scripts."""
    _, name, line = script[i]
    if name not in scan.classes or not _may_name_class(script, i):
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


def _file_read_call(scan: _Scan, path: str, script: list, i: int) -> bool:
    """Whether script[i] is a FileAccess call; if so, record the file it reads."""
    _, api, line = script[i]
    if api != "FileAccess" or not _is_member_call(script, i):
        return False
    literal = _literal_argument(script, i + 3, constants=scan.constants.get(path))
    if _names_resource(literal) and script[i + 2][1] in _FILE_READS:
        kind = "file_access" if literal else "dynamic_file_access"
        scan.reference(path, literal, kind, line)
    return True


def _directory_listing_call(scan: _Scan, path: str, script: list, i: int) -> bool:
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


_SHADER_FORMATS = (".gdshader", ".gdshaderinc", ".shader", ".shaderinc")


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
        elif path == PROJECT_FILE:
            _scan_project(scan, path, text)


# ==== Graph ===================================================================


_IMPORT_KINDS = frozenset({"gltf_buffers", "gltf_images", "import_settings"})

# Godot records no file or directory hint for a setting, and a declared runtime
# reference names what code lists. Every other kind loads or reads one file.
DIRECTORY_REFERENCE_KINDS = frozenset({"project_setting", "runtime"})


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
    base = PROJECT_FILE if edge["kind"] == "load" else edge["source"]
    return res_path(reference, base)


def _below(nodes: Iterable[str], directory: str) -> list[str]:
    """The sorted nodes below a directory's res:// path."""
    prefix = directory + "/"
    return sorted(path for path in nodes if path.startswith(prefix))


def _directories(nodes: Iterable[str]) -> set[str]:
    """Every directory below which the project declares a file."""
    directories = set()
    for path in nodes:
        parent = path.rpartition("/")[0]
        while parent != "res:/" and parent not in directories:
            directories.add(parent)
            parent = parent.rpartition("/")[0]
    return directories


def edge_targets(edge: dict) -> list[str]:
    """The nodes a resolved edge reaches: its file, or every node below its directory."""
    return edge.get("targets", [edge["target"]])


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
        return not any(nodes[path]["membership"] for path in edge_targets(edge))


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
    diagnostics = sorted_diagnostics(scan.diagnostics)
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
            "project_configuration": PROJECT_FILE,
            "ignored": "files Godot never scans: hidden, or below a directory that holds a .gdignore or a project.godot",
            "custom_loaders_analyzed": False,
        },
        "complete": not coverage["unsupported"]
        and not any(edge["status"] != "resolved" for edge in edges)
        and not any(item["severity"] == "error" for item in diagnostics),
        "limits": [
            "static literals and literal constants only; no program evaluation",
            "global class symbols are conservative",
            "unrecognized formats and custom loaders are not analyzed",
            "file-level reachability cannot prove non-use",
        ],
    }


def _undeclared_addon_use(
    edge: dict, nodes: dict, addon_of: dict, uses: dict
) -> dict | None:
    """The warning for a content file that refers to a file of an add-on it does not use."""
    if edge["status"] != "resolved":
        return None
    source_owner = nodes[edge["source"]].get("owner", "")
    if not source_owner or source_owner in addon_of:
        return None
    for target in edge_targets(edge):
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


def is_inferred_runtime(edge: dict) -> bool:
    """Whether the scanner inferred a runtime reference, rather than the build or a declaration."""
    return edge["origin"] == "inferred" and edge["dependency_kind"] == "runtime"


def _is_undeclared(edge: dict) -> bool:
    """Whether a file's inferred runtime reference lacks a runtime_references entry."""
    if edge["status"] != "resolved" or edge["source"] == PROJECT_FILE:
        return False
    return is_inferred_runtime(edge) and not edge["declared"]


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
        diagnostics=sorted_diagnostics(diagnostics + undeclared),
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


# ==== Single files ============================================================


class _AnySource:
    """Every path, as the source a sidecar may author an identity for."""

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
        path = _candidate_path(edge)
    except ValueError:
        path = None
    return {"kind": edge["kind"], "path": path, "uid": _uid_of(edge)}


def file_references(path: str, text: str) -> dict:
    """
    What one file at a res:// path declares and references on its own, without its project.

    The result holds the UIDs the file authors, a sidecar's for its file; the global classes
    a script declares, the one it extends by name and every name it may use as a global
    class; and the references the graph records, each with its kind, its normalized path and
    its UID. Gazelle's Godot language derives dependencies from it.
    """
    scan = _Scan(Path.cwd())
    scan.nodes[path] = {"path": path}
    scan.texts[path] = text
    _scan_declarations(scan)
    _scan_references(scan)
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
