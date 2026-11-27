"""
The files an operation stages for its project: the members and import inputs, overlaid by
the import results, the extension list and the text files the metadata index completes.

Sections: Staged paths, Import results, Metadata completion, Staged files.
"""

import json
from collections.abc import Callable, Collection, Iterable
from pathlib import Path, PurePosixPath

from tools.inputs.manifest import resource_path
from tools.inputs.originals import Original, read_original, tree_entries
from tools.resources.files import EXTENSION_LIST, is_uid_sidecar
from tools.resources.node_ids import with_node_ids
from tools.resources.text import portable_identity, validate_identities
from tools.resources.uids import with_resource_uids

# ==== Staged paths ============================================================


def _check_prefixes(path: str, files: dict[str, str], prefixes: dict[str, str]) -> None:
    """
    Check each prefix of path against the prefixes seen so far and the files.

    A prefix may have one spelling, and only the path itself may be a file.
    """
    parts = resource_path(path).split("/")
    for index in range(1, len(parts) + 1):
        prefix = "/".join(parts[:index])
        identity = portable_identity(prefix)
        previous = prefixes.setdefault(identity, prefix)
        if previous != prefix:
            raise ValueError(
                f"Conflicting portable Godot paths: {previous!r} and {prefix!r}"
            )
        if index < len(parts) and identity in files:
            raise ValueError(
                f"Conflicting Godot file/directory paths: {files[identity]!r} and {path!r}"
            )


def validate_staged_paths(resource_paths: dict[str, str]) -> None:
    """Detect portable-path collisions before a case-insensitive copy can lose data."""
    prefixes: dict[str, str] = {}
    files = {portable_identity(path): path for path in resource_paths}
    for path in resource_paths:
        _check_prefixes(path, files, prefixes)


# ==== Import results ==========================================================


def _check_import_uid(
    relative: str, original: Original, resource_paths: dict[str, str], execroot: Path
) -> None:
    """Fail for a cached UID sidecar that differs from an authored one at its path."""
    if not is_uid_sidecar(relative) or relative not in resource_paths:
        return
    authored = (execroot / resource_paths[relative]).read_text(encoding="utf-8").strip()
    if authored != read_original(original).decode("utf-8").strip():
        raise ValueError("Cached import UID conflicts with authored sidecar: " + relative)


def _merged_import_results(
    imported_files: list[tuple[str, Original, str]],
    resource_paths: dict[str, str],
    execroot: Path,
) -> dict[str, Original]:
    """
    The import results by resource path; equal results of several units merge.

    An import result may differ neither from another unit's nor, for a UID sidecar, from
    the authored one.
    """
    merged: dict[str, Original] = {}
    for relative, original, _ in imported_files:
        _check_import_uid(relative, original, resource_paths, execroot)
        if relative not in merged:
            merged[relative] = original
        elif read_original(merged[relative]) != read_original(original):
            raise ValueError(
                f"Conflicting import results for {PurePosixPath(relative).name}"
            )
    return merged


# ==== Metadata completion =====================================================


# How each kind of metadata completes a text file from its metadata index entry.
COMPLETIONS = {
    "node_ids": lambda text, path, _: with_node_ids(text, path),
    "resource_uids": lambda text, path, entry: with_resource_uids(
        text, path, entry["uids"]
    ),
}


def completed_texts(
    index: dict, kinds: Iterable[str], staged: Collection[str], read: Callable[[str], str]
) -> dict[str, str]:
    """
    Return the staged text files the metadata kinds of the index change, completed.

    Args:
        index: The metadata index.
        kinds: The kinds of metadata to complete, keys of COMPLETIONS.
        staged: The staged resource paths; the index may name others.
        read: Returns a staged file's text by its resource path.
    """
    texts: dict[str, str] = {}
    authored: dict[str, str] = {}
    for kind in kinds:
        for path, entry in index[kind].items():
            if path not in staged:
                continue
            if path not in texts:
                texts[path] = authored[path] = read(path)
            texts[path] = COMPLETIONS[kind](texts[path], path, entry)
    return {path: text for path, text in texts.items() if text != authored[path]}


def _metadata_completions(
    metadata: dict, execroot: Path, files: dict[str, Original]
) -> dict[str, Original]:
    """The staged text files the metadata index completes, as bytes."""
    index = json.loads((execroot / metadata["path"]).read_text(encoding="utf-8"))
    texts = completed_texts(
        index,
        metadata["assign"],
        files,
        lambda path: read_original(files[path]).decode("utf-8"),
    )
    return {path: text.encode("utf-8") for path, text in texts.items()}


# ==== Staged files ============================================================


def _source_paths(manifest: dict) -> dict[str, str]:
    """The import inputs overlaid by the members, which must not stage other files there."""
    resource_paths = dict(manifest.get("import_resource_paths", {}))
    for path, source in manifest["member_resource_paths"].items():
        if resource_paths.setdefault(path, source) != source:
            raise ValueError("Import input conflicts with project member: " + path)
    return resource_paths


def extension_list(paths: Iterable[str]) -> bytes:
    """EXTENSION_LIST's content for the .gdextension files among paths; empty for none."""
    extensions = sorted(path for path in paths if path.endswith(".gdextension"))
    return "".join("res://" + path + "\n" for path in extensions).encode("utf-8")


def staged_files(manifest: dict, execroot: Path) -> dict[str, Original]:
    """
    Return the files the project stages, project.godot aside: where each one's bytes come from.

    The members and import inputs, overlaid by the import results, then the extension list and
    the text files the metadata index completes, as bytes. Conflicting paths, import results
    or UIDs fail here, so every operation staging the project rejects the same inputs.
    """
    resource_paths = _source_paths(manifest)
    imported_files = [
        (relative, original, tree)
        for tree in manifest.get("imports", [])
        for relative, original in tree_entries(execroot / tree)
    ]
    # Validate the complete namespace once. Cached sidecars and generated files must not
    # alias authored paths or another import result.
    validate_staged_paths(
        resource_paths | {relative: tree for relative, _, tree in imported_files}
    )
    validate_identities(
        {path: execroot / source for path, source in resource_paths.items()}
    )
    files: dict[str, Original] = {
        relative: execroot / source for relative, source in resource_paths.items()
    }
    files |= _merged_import_results(imported_files, resource_paths, execroot)
    # Load extensions before the file scan so imports and exported scripts
    # see the same registered classes, including on a cold build.
    content = extension_list(resource_paths)
    if content:
        files[EXTENSION_LIST] = content
    if "metadata_index" in manifest:
        files.update(_metadata_completions(manifest["metadata_index"], execroot, files))
    return files
