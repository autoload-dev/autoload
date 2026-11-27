"""
Write a pack's PCK without Godot: its files as they are, with what Godot's export generates.

The PCK holds what Godot's export packs with scripts as text and without text-to-binary
conversion (preset script_export_mode 0, editor/export/convert_text_resources_to_binary
false): the pack's text scenes, resources and scripts, each imported file's .import file
with its imported files for the export's feature tags, and the caches the runtime reads:
the global script classes, the UIDs and the extension list. The configuration export
supplies project.binary, the text server's support data and the feature tags.
"""

import argparse
import functools
import json
from collections.abc import Mapping
from pathlib import Path

from tools.class_fragment import CACHE as CLASS_CACHE
from tools.class_fragment import class_cache, fragment
from tools.godot_files import IMPORT, UID, hidden_by, is_sidecar_named
from tools.godot_staging import (
    add_manifest_arguments,
    extension_list,
    load_manifest,
    open_original,
    read_original,
    staged_files,
)
from tools.pack_contents import content_selection, write_report
from tools.pck import EXTENSION_LIST, Content, engine_version, pck_files, write_pck
from tools.resource_text import IMPORTER, REMAP_PATH, remap_section
from tools.resource_uids import declares_uids, known_uids, uid_cache

UID_CACHE = ".godot/uid_cache.bin"


def exported_import(text: str, features: set[str]) -> tuple[str, list[str]]:
    """
    Return the .import file Godot's export packs and the imported files it names.

    Godot keeps the remap section without the keys of feature tags the export lacks,
    and erases the other sections (editor/export/editor_export_platform.cpp:1642-1704
    in Godot 4.7.2); the runtime reads only the remap section.
    """
    body = remap_section(text)
    if body is None:
        raise ValueError("no [remap] section")
    imported = []
    for match in REMAP_PATH.finditer(body):
        feature = match[2]
        if feature is None or feature in features:
            imported.append(match[3])
        else:
            body = body.replace(match[0] + "\n", "", 1)
    return body.rstrip("\n") + "\n", imported


def raw_path(setting: str, uids: Mapping[str, str]) -> str:
    """Return a setting's file as a resource path, resolving a uid:// value."""
    if setting.startswith("uid://"):
        return next((path for path, uid in uids.items() if uid == setting), "")
    return setting.removeprefix("res://")


def pack_files(
    manifest: dict, execroot: Path, facts: dict, selected: set[str]
) -> dict[str, Content]:
    """
    Return the PCK's files by path.

    Args:
        manifest: The writer's manifest, with its imports.
        execroot: Where the manifest's paths are.
        facts: The configuration export's facts.
        selected: The paths the pack's content selects.
    """
    staged = staged_files(manifest, execroot)
    ignored = set(manifest.get("ignored_paths", []))
    declared = selected | ignored
    left_out = {path for path in ignored if hidden_by(path, declared)}
    texts: dict[str, str] = {}

    def text(path: str) -> str:
        if path not in texts:
            texts[path] = read_original(staged[path]).decode("utf-8")
        return texts[path]

    def original(path: str) -> Content:
        source = staged[path]
        return (
            source
            if isinstance(source, bytes)
            else functools.partial(open_original, source)
        )

    files = {
        path: original(path)
        for path in selected
        if path in staged and path not in left_out and not path.endswith(IMPORT)
    }
    # The UIDs staging gave files without an authored .uid sidecar, which Godot packs.
    for path in list(files):
        sidecar = path + UID
        if not is_sidecar_named(path) and sidecar in staged:
            files.setdefault(sidecar, original(sidecar))
    features = set(facts["features"])
    owners = set()
    for path in sorted(files):
        if is_sidecar_named(path) or path + IMPORT not in staged:
            continue
        import_text = text(path + IMPORT)
        importer = IMPORTER.search(import_text)
        kind = importer[1] if importer else ""
        if kind == "keep":
            continue
        del files[path]
        if kind == "skip":
            continue
        owners.add(path)
        try:
            exported, imported = exported_import(import_text, features)
        except ValueError as error:
            raise ValueError(f"res://{path}{IMPORT}: {error}") from error
        files[path + IMPORT] = exported.encode("utf-8")
        for target in imported:
            if target not in staged:
                raise ValueError(
                    f"res://{path}{IMPORT} names res://{target}, which its import did not produce"
                )
            files[target] = original(target)
    uids = known_uids(
        {
            path: text(path)
            for path in staged
            if declares_uids(path)
            and (path in files or path.removesuffix(IMPORT) in owners)
        },
        {path for path in files if not is_sidecar_named(path)} | owners,
    )
    for setting in (facts.get("icon", ""), facts.get("boot_splash", "")):
        # The runtime reads the icon and the boot splash as image files, not as
        # imported textures (editor_export_platform.cpp:1246-1257).
        path = raw_path(setting, uids)
        if path in staged:
            files.setdefault(path, original(path))
    scripts = {path: text(path) for path in files if path.endswith(".gd")}
    # The files read for the caches go in from memory rather than being read again.
    for path, read in texts.items():
        if path in files and not isinstance(files[path], bytes):
            files[path] = read.encode("utf-8")
    files[CLASS_CACHE] = class_cache([fragment(scripts)]).encode("utf-8")
    files[UID_CACHE] = uid_cache(uids)
    extensions = extension_list(files)
    if extensions:
        files[EXTENSION_LIST] = extensions
    files.update(pck_files(execroot / manifest["configuration"]))
    return files


def write(manifest: dict, output: Path, report: Path, execroot: Path) -> None:
    facts = json.loads(
        (execroot / manifest["configuration_facts"]).read_text(encoding="utf-8")
    )
    selection = content_selection(manifest, execroot)
    files = pack_files(manifest, execroot, facts, selection[0])
    write_pck(output, files, engine_version(manifest["version"]))
    write_report(report, manifest, selection, files, output, "none")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_manifest_arguments(parser)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    execroot = Path.cwd()
    write(load_manifest(args), args.output.absolute(), args.report.absolute(), execroot)


if __name__ == "__main__":
    main()
