"""
A project's resource graph: which of its declared files reference which, as far as static
reading tells. It never discovers Bazel action inputs.

Graph paths are res:// identities, not execroot paths. The scanner deliberately runs no
Godot, scripts, importers or add-on code. Unknown dynamic loads stay diagnostics, and
explicit declarations must cover them.

The scanner (scan.py) finds what each file declares and references. This module resolves
those references between the project's declared files. selection.py selects a pack's
resources from the graph, and command.py scans, checks and queries graphs (query.py).

Sections: Declared files, Graph.
"""

import json
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from tools.resource_graph.diagnostics import diagnostic, sorted_diagnostics, warning
from tools.resource_graph.scan import (
    Scan,
    candidate_path,
    scan_declarations,
    scan_references,
    uid_of,
)
from tools.resources.text import (
    ANALYZED_FORMATS,
    LEAF_FORMATS,
    PROJECT_FILE,
    portable_identity,
    res_path,
)

# ==== Declared files ==========================================================


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


def _declared_sources(manifest: dict, scan: Scan) -> tuple[dict, dict]:
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


def _flag_format(scan: Scan, path: str, suffix: str, analysis: str) -> None:
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


def _read_text(scan: Scan, path: str, source: str) -> None:
    try:
        scan.texts[path] = (scan.execroot / source).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        scan.error("unreadable_source", path, str(error))


def _declare_nodes(scan: Scan, manifest: dict, sources: dict, members: set[str]) -> None:
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


def _add_generated_uids(scan: Scan, uids: dict[str, str]) -> None:
    """Identify the files without an authored UID by the UID the index records for them."""
    identified = {owner for owners in scan.uids.values() for owner in owners}
    for owner, uid in uids.items():
        node = "res://" + owner
        if node in scan.nodes and node not in identified:
            scan.uids[uid].add(node)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_metadata_index(scan: Scan, manifest: dict) -> dict[str, set[str]]:
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


def _assign_uids(scan: Scan) -> None:
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


def _diagnose_conflicting_uids(scan: Scan) -> None:
    for path, node in sorted(scan.nodes.items()):
        if len(node["uids"]) > 1:
            scan.error(
                "conflicting_uids",
                path,
                "resource has multiple authored identities: " + ", ".join(node["uids"]),
            )


def _diagnose_duplicate_classes(scan: Scan) -> None:
    for name, paths in sorted(scan.classes.items()):
        if len(paths) > 1:
            scan.error(
                "duplicate_class",
                min(paths),
                name + " belongs to multiple scripts: " + ", ".join(sorted(paths)),
            )


def _declare_runtime_references(scan: Scan, manifest: dict) -> set[tuple[str, str]]:
    """Add the declared runtime references; returns their (source, target) pairs."""
    declared = set()
    for relation in manifest.get("relationships", []):
        if relation["kind"] != "runtime" or not relation["source"]:
            continue
        source = res_path(relation["source"])
        target = res_path(relation["target"])
        declared.add((source, target))
        scan.link(source, target, "runtime", "declared")
        if source not in scan.nodes:
            scan.error(
                "missing_declared_source",
                source,
                "runtime declaration source is not in this project",
            )
    return declared


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
        self, scan: Scan, declared: set[tuple[str, str]], corrected: dict[str, set[str]]
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
        uid = uid_of(edge)
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
            candidate = candidate_path(edge)
        except ValueError as error:
            self._error(edge, "invalid_reference", str(error) + ": " + reference)
            return "invalid"
        owners = self._owners(edge)
        if len(owners) > 1:
            self._error(
                edge,
                "ambiguous_uid_reference",
                f"UID has multiple owners: {uid_of(edge)}",
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
            f"{edge['reference']} and {uid_of(edge)} identify different declared resources"
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


def _graph_document(manifest: dict, scan: Scan, edges: list[dict]) -> dict:
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
    manifest: dict, scan: Scan, edges: list[dict]
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
    scan = Scan(execroot or Path.cwd())
    sources, members = _declared_sources(manifest, scan)
    _declare_nodes(scan, manifest, sources, {res_path(path) for path in members})
    scan_declarations(scan)
    corrected = _read_metadata_index(scan, manifest)
    _assign_uids(scan)
    _diagnose_conflicting_uids(scan)
    _diagnose_duplicate_classes(scan)
    scan_references(scan)
    declared = _declare_runtime_references(scan, manifest)
    resolver = _Resolver(scan, declared, corrected)
    for edge in scan.edges:
        resolver.resolve(edge)
    edges = _unique_edges(scan.edges)
    _diagnose_undeclared_addon_uses(manifest, scan, edges)
    graph = _graph_document(manifest, scan, edges)
    return require_declared(graph) if manifest.get("require_declared") else graph
