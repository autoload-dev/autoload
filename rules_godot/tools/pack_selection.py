"""
Select a pack's resources from its project's resource graph and check that what they
reference is available.

A tool of its own beside resource_graph.py, whose graph it reads, so a change to selection
reruns only selections.

Sections: Selection, Command line.
"""

import argparse
import json
import sys
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path, PurePosixPath

from tools.godot_files import DIRECTORY_MARKERS, hidden_by
from tools.resource_graph import (
    Findings,
    edge_targets,
    format_diagnostic,
    is_inferred_runtime,
    read_json,
    read_manifest,
    sorted_diagnostics,
)
from tools.resource_graph_query import chain, file_pairs
from tools.resource_text import PROJECT_FILE, res_path

# ==== Selection ===============================================================


# Code can guard these runtime accesses, so an unavailable target is not
# necessarily an error. Every other reference must resolve wherever it loads.
SOFT_REFERENCE_KINDS = frozenset({"load", "file_access", "runtime", "runtime_deps"})


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
    return {(s, t) for s, t in file_pairs(edges) if t in hidden}


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


class _PackSelection(Findings):
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
        if PROJECT_FILE in self.nodes:
            self._reach(PROJECT_FILE, None, "project")
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
        resources = sorted(self.parents.keys() - {PROJECT_FILE})
        return {
            "diagnostics": diagnostics,
            "mode": "reachable" if self.reachable else "members",
            "resources": resources,
            "chains": {path: chain(self.parents, path) for path in resources}
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
        return sorted_diagnostics(list(unique.values()))

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
        if cause is None or not is_inferred_runtime(edge):
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
            for target in edge_targets(edge):
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
    required = [read_json(execroot / content) for content in manifest["required"]]
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


# ==== Command line ============================================================


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _run(args: argparse.Namespace) -> int:
    selection, content = select_from_manifest(
        read_json(args.manifest),
        read_json(args.graph),
        read_manifest(args.project_manifest),
        args.execroot,
    )
    args.output.write_text(_json(selection), encoding="utf-8")
    args.content.write_text(_json(content), encoding="utf-8")
    for item in selection["diagnostics"]:
        print(format_diagnostic(item), file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, required=True, help="the pack's selection manifest"
    )
    parser.add_argument(
        "--graph", type=Path, required=True, help="the project's resource graph"
    )
    parser.add_argument(
        "--project-manifest",
        type=Path,
        required=True,
        help="the manifest the project's graph was scanned from",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="selection report with explanation chains",
    )
    parser.add_argument(
        "--content",
        type=Path,
        required=True,
        help="resources this pack provides to dependent packs",
    )
    parser.add_argument("--execroot", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
