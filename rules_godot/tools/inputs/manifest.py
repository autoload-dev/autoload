"""
The action manifest, the entire input set of one build tool's action, with the resource
path manifests and import results that reach it as arguments, and its resource paths.

Sections: Resource paths, Manifest.
"""

import argparse
import json
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from tools.inputs.mapped_paths import add_root_arguments, resolve_paths, resolver

# ==== Resource paths ==========================================================


def _is_resource_path(value: str) -> bool:
    """Whether value is a relative POSIX path of plain components and printable text."""
    if not value or PurePosixPath(value).is_absolute():
        return False
    if "\\" in value or ":" in value:
        return False
    if any(ord(c) < 32 for c in value):
        return False
    return not any(x in ("", ".", "..") for x in value.split("/"))


def resource_path(value: str) -> str:
    if not _is_resource_path(value):
        raise ValueError(f"Invalid resource path: {value!r}")
    return value


# ==== Manifest ================================================================


def add_resource_path_manifests(
    manifest: dict, paths: list[Path], resolve: Callable[[str], str]
) -> None:
    """Merge resource path manifests of more paths to stage into the manifest's members."""
    resource_paths = manifest.setdefault("member_resource_paths", {})
    for path in paths:
        staged = json.loads(path.read_text(encoding="utf-8"))
        for relative, source in resolve_paths(staged, resolve).items():
            if resource_paths.setdefault(relative, source) != source:
                raise ValueError("Conflicting staged sources for " + relative)


def add_manifest_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the manifest, output and staging arguments every action takes."""
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--resource-path-manifest",
        dest="resource_path_manifests",
        action="append",
        default=[],
        type=Path,
        help="Resource path manifest of more paths to stage.",
    )
    parser.add_argument(
        "--import",
        dest="imports",
        action="append",
        default=[],
        help="Import result to stage, in order.",
    )
    parser.add_argument(
        "--editor", help="The editor executable, for actions that run it."
    )
    add_root_arguments(parser)


def load_manifest(args: argparse.Namespace) -> dict:
    """Read the action manifest and add the staged imports and resource paths."""
    resolve = resolver(args.roots)
    manifest = resolve_paths(
        json.loads(args.manifest.read_text(encoding="utf-8")), resolve
    )
    manifest["imports"] = args.imports
    if args.editor:
        manifest["editor"] = args.editor
    add_resource_path_manifests(manifest, args.resource_path_manifests, resolve)
    return manifest
