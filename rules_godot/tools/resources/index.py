"""
Index the metadata a project's text files lack, once per project.

The index holds the UIDs the project's files declare, the scenes that declare
nodes without a unique_id and the text resources whose references lack the
UID of the file they name, with those UIDs. Packs complete their staged copy
from it, packs that require the metadata check it, and godot_metadata_sync
writes it into the checkout.

It reads the project's .tscn, .tres, .uid and .import members and the import
results, but not the initialization, so script edits leave it current.
"""

import argparse
import json
import sys
from pathlib import Path

from tools.godot_staging import open_original, tree_entries
from tools.resources.files import is_sidecar_named
from tools.resources.node_ids import missing_node_ids
from tools.resources.uids import (
    TEXT_RESOURCES,
    known_uids,
    reference_updates,
    uid_sources,
)

# What a file lacking each kind of metadata has.
LACKS = {
    "node_ids": "scene nodes without unique_id",
    "resource_uids": "references without the UID of the file they name",
}


def build_index(files: dict[str, str], members: set[str]) -> dict:
    """
    Return the index of files' texts by resource path.

    Each kind maps a file to its entry: the issues it has and, for resource
    UIDs, the UIDs its references need.

    Args:
        files: Texts of the .tscn, .tres, .uid and .import files, generated
            sidecars included.
        members: The project's member resource paths; a sidecar identifies only a member.
    """
    uids = known_uids(files, members)
    texts = {
        path: text
        for path, text in sorted(files.items())
        if path.endswith(TEXT_RESOURCES)
    }
    node_ids, resource_uids = {}, {}
    for path, text in texts.items():
        if path.endswith(".tscn") and (nodes := missing_node_ids(text)):
            node_ids[path] = {"issues": nodes}
        issues, needed = reference_updates(text, path, uids)
        if issues:
            resource_uids[path] = {"issues": issues, "uids": needed}
    return {"uids": uids, "node_ids": node_ids, "resource_uids": resource_uids}


def problems(index: dict, kind: str, paths: list[str]) -> dict[str, list[str]]:
    """Return what the files at paths lack of kind: nodes or references, by path."""
    return {
        path: index[kind][path]["issues"] for path in sorted(paths) if path in index[kind]
    }


def lacking(subject: str, kind: str, found: dict[str, list[str]], remedy: str) -> str:
    """Describe what subject's files lack, as packs and godot_metadata_sync's test report it."""
    listing = "\n".join(
        f"  res://{path}: {', '.join(issues[:3])}"
        + (f" and {len(issues) - 3} more" if len(issues) > 3 else "")
        for path, issues in found.items()
    )
    return f"{subject} has {LACKS[kind]}:\n{listing}\n{remedy}"


def _index(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Index a project's metadata.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--import",
        dest="imports",
        action="append",
        default=[],
        type=Path,
        help="Import result directory; repeated.",
    )
    args = parser.parse_args(arguments)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    files = {}
    for tree in args.imports:
        for path, original in tree_entries(tree):
            if is_sidecar_named(path):
                with open_original(original) as data:
                    files[path] = data.read().decode("utf-8")
    files.update(
        uid_sources({path: Path(source) for path, source in manifest["files"].items()})
    )
    index = build_index(files, set(manifest["members"]))
    args.output.write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _check(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(
        description="Fail while a pack's files lack metadata."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(arguments)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    index = json.loads(Path(manifest["index"]).read_text(encoding="utf-8"))
    kind = manifest["kind"]
    if found := problems(index, kind, manifest["checked"]):
        sys.exit(
            lacking(
                manifest["pack"],
                kind,
                found,
                "Commit the values with bazel run on a godot_metadata_sync target of "
                f"{manifest['project']}, or let the build add them to its copy with "
                f"--@autoload_rules_godot//godot/metadata:{kind}=assign.",
            )
        )
    args.output.write_text("", encoding="utf-8")


def main() -> None:
    commands = {"index": _index, "check": _check}
    if sys.argv[1:2] and sys.argv[1] in commands:
        commands[sys.argv[1]](sys.argv[2:])
        return
    sys.exit("usage: metadata_index index|check --manifest FILE --output FILE")


if __name__ == "__main__":
    main()
