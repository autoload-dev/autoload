"""
List, write or check the metadata a project's checkout files lack.

That is the .uid and .import sidecars the build generated, the unique_id of
every node a text scene declares without one and the UID of every file an
ext_resource names.
"""

import argparse
import json
import sys
from collections.abc import Collection
from pathlib import Path

from tools.checkout.sync import Runfile, sync_main
from tools.inputs.originals import open_original
from tools.inputs.runfiles import report, tree_files_by_path
from tools.resources.files import sidecar_source
from tools.resources.index import lacking
from tools.staging.files import COMPLETIONS


def list_sidecars(
    checkout: dict[str, list[str]], imports: list[str], initialized: list[str]
) -> list[dict]:
    """
    List the sidecars the build generated for checkout files that declare none.

    Args:
        checkout: Resource paths of checkout files to their workspace paths and
            the labels declaring them.
        imports: The project's import results.
        initialized: The project's initialization trees.

    Returns:
        One sidecar entry per sidecar, by resource path: its workspace path
        beside its file, the label declaring the file and its text.
    """
    sidecars = []
    for path, original in sorted(tree_files_by_path(imports, initialized).items()):
        source = sidecar_source(path)
        if source not in checkout or path in checkout:
            continue
        workspace, owner = checkout[source]
        with open_original(original) as data:
            content = data.read().decode("utf-8")
        sidecars.append(
            {
                "kind": "sidecar",
                "path": path,
                "workspace": workspace + path[len(source) :],
                "owner": owner,
                "content": content,
            }
        )
    return sidecars


def index_updates(
    checkout: dict[str, list[str]], index: dict, kinds: Collection[str]
) -> list[dict]:
    """
    List the checkout's text files the metadata index names for the kinds written.

    Args:
        checkout: Resource paths of checkout files to their workspace paths and
            the labels declaring them.
        index: The project's metadata index.
        kinds: The metadata kinds godot_metadata_sync writes.

    Returns:
        One entry per file and kind: its resource and workspace paths, the label
        declaring it and its index entry. Writing applies it to the file's text then.
    """
    return [
        {
            "kind": kind,
            "path": path,
            "workspace": checkout[path][0],
            "owner": checkout[path][1],
        }
        | entry
        for kind in sorted(kinds)
        for path, entry in sorted(index[kind].items())
        if path in checkout
    ]


# What the reports call each kind of metadata written.
_WRITTEN = {"node_ids": "node IDs", "resource_uids": "resource UIDs"}


def place_metadata(entries: list[dict], workspace: Path, *, write: bool) -> list[dict]:
    """
    Write missing metadata into the checkout and name the sidecars to declare.

    A sidecar entry creates its file; an update entry updates its file's
    current text.

    Args:
        entries: Entries of list_sidecars and index_updates.
        workspace: The checkout's root directory.
        write: Whether to write the missing ones.

    Returns:
        The entries still missing.
    """
    missing = []
    for entry in entries:
        target, owner, path = entry["workspace"], entry["owner"], entry["path"]
        destination = workspace / target
        if entry["kind"] in COMPLETIONS:
            if write:
                complete = COMPLETIONS[entry["kind"]]
                # newline="" keeps the file's own line endings.
                text = destination.read_text(encoding="utf-8", newline="")
                destination.write_text(
                    complete(text, path, entry), encoding="utf-8", newline=""
                )
                report(f"wrote {_WRITTEN[entry['kind']]} into {target}; commit it")
            else:
                missing.append(entry)
        elif destination.exists():
            report(f"{target} is not declared; declare it in {owner} as res://{path}")
        elif write:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(entry["content"], encoding="utf-8")
            report(f"wrote {target}; commit it and declare it in {owner} as res://{path}")
        else:
            missing.append(entry)
    return missing


def check_metadata(
    entries: list[dict], writer: str, *, required: Collection[str] = ()
) -> int:
    """
    Name each sidecar the checkout lacks or does not declare; fail if there is one.

    Update entries count only for the kinds of metadata required, reported as
    packs that require them report them.
    """
    missing = [entry for entry in entries if entry["kind"] == "sidecar"]
    for sidecar in missing:
        report(
            f"{sidecar['workspace']} is missing or not declared; write it with "
            f"bazel run {writer} and declare it in {sidecar['owner']} as "
            f"res://{sidecar['path']}"
        )
    lacks = False
    for kind in sorted(required):
        if found := {e["path"]: e["issues"] for e in entries if e["kind"] == kind}:
            lacks = True
            report(
                lacking(
                    "The checkout",
                    kind,
                    found,
                    f"Commit the values with bazel run {writer}.",
                )
            )
    return 1 if missing or lacks else 0


def _list(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(description="List a project's missing metadata.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--initialized", required=True)
    parser.add_argument("--import", dest="imports", action="append", default=[])
    parser.add_argument(
        "--update",
        action="append",
        default=[],
        choices=sorted(COMPLETIONS),
        help="Metadata to write into checkout text files.",
    )
    parser.add_argument("--index", type=Path, help="The project's metadata index.")
    args = parser.parse_args(arguments)
    checkout = json.loads(args.manifest.read_text(encoding="utf-8"))["checkout"]
    entries = list_sidecars(checkout, args.imports, [args.initialized])
    if args.update:
        index = json.loads(args.index.read_text(encoding="utf-8"))
        entries += index_updates(checkout, index, args.update)
    args.output.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def _check(manifest: dict, runfile: Runfile) -> int:
    entries = json.loads(runfile(manifest["metadata"]).read_text(encoding="utf-8"))
    return check_metadata(entries, manifest["writer"], required=manifest["required"])


def _write(manifest: dict, runfile: Runfile, workspace: Path) -> None:
    entries = json.loads(runfile(manifest["metadata"]).read_text(encoding="utf-8"))
    try:
        place_metadata(entries, workspace, write=True)
    except OSError as error:
        report(str(error))
        raise SystemExit(1) from None


def main() -> None:
    if sys.argv[1:2] == ["list"]:
        _list(sys.argv[2:])
        return
    sync_main(__doc__ or "", _check, _write, "metadata")


if __name__ == "__main__":
    main()
