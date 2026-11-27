"""
The command line of //tools/resource_graph: scan a project's declared files into its resource
graph, check a graph, and query one (maintainer-tools.md).
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tools.resource_graph.graph import (
    build_graph,
    format_diagnostic,
    read_json,
    read_manifest,
    require_declared,
)
from tools.resource_graph.query import query_graph


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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
    graph = read_json(args.graph)
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
    graph = read_json(args.graph)
    previous = read_json(args.previous_graph) if args.previous_graph else None
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for add_command in (_scan_command, _check_command, _query_command):
        add_command(commands)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
