"""
File-level reachability over a resource graph: which files a file reaches, or which files a
change affects, each with its shortest explanation chain. Maintainers query a graph with
`bazel run //tools/resource_graph -- query`; no build action reads it.
"""

from collections import defaultdict, deque
from collections.abc import Iterable, Iterator

from tools.resource_graph.graph import edge_targets
from tools.resources.text import PROJECT_FILE, res_path


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


def file_pairs(edges: Iterable[dict]) -> Iterator[tuple[str, str]]:
    """The (source, target) files of each resolved edge."""
    for edge in edges:
        if edge["status"] == "resolved":
            for target in edge_targets(edge):
                yield edge["source"], target


def _adjacency(edges: Iterable[dict], reverse: bool) -> defaultdict[str, set[str]]:
    """The files each file reaches through its resolved edges, or is reached from if reversed."""
    adjacency = defaultdict(set)
    for source, target in file_pairs(edges):
        start, end = (target, source) if reverse else (source, target)
        adjacency[start].add(end)
    return adjacency


def chain(parents: dict, path: str | None) -> list[str]:
    """The path from a root to path, following each file's parent."""
    result = []
    while path is not None:
        result.append(path)
        path = parents.get(path)
    return result[::-1]


def _parents(
    roots: set[str],
    known: set[str],
    adjacency: defaultdict[str, set[str]],
    reverse: bool,
) -> dict[str, str | None]:
    """The file each reached file was first reached from, breadth first; roots have none."""
    parents = {value: None for value in sorted(roots)}
    if reverse and PROJECT_FILE in roots:
        # Project settings can influence every import and script. Static source
        # references alone do not describe that configuration dependency.
        parents.update(
            {value: PROJECT_FILE for value in sorted(known) if value not in parents}
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
        "chains": {path: chain(parents, path) for path in sorted(parents)},
        "conservative": True,
        "complete": graph["complete"],
    }
