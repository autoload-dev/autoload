"""
What a pack contains: its selected and excluded paths, and the check of a written PCK.

Shared by the pack's Godot export and its writer without Godot, so neither tool's
actions rerun when the other changes.
"""

import json
from collections.abc import Collection
from pathlib import Path

from tools.digest import digest
from tools.godot_files import IMPORT, REMAP, UID, is_sidecar_named


def excluded_with_sidecars(excluded: Collection[str]) -> set[str]:
    """Excluded paths plus the .uid files Godot writes beside scripts and shaders."""
    return {
        *excluded,
        *(path + UID for path in excluded if not is_sidecar_named(path)),
    }


def inspect_export(
    contents: dict,
    selected: set[str],
    excluded: set[str],
    ignored: Collection[str] = (),
) -> dict:
    """
    Report the actual PCK directory, including Godot's remapped resources.

    Godot exports no file of ignored, the staged files it ignores; a hidden one of a
    visible directory it may still pack, so none of them is required.
    """
    paths = {path.removeprefix("res://") for path in contents["paths"]}

    def packed(path: str) -> bool:
        return any(
            candidate in paths for candidate in (path, path + REMAP, path + IMPORT)
        )

    leaked = sorted(path for path in excluded_with_sidecars(excluded) if packed(path))
    if leaked:
        raise RuntimeError(
            "Godot included excluded resources in the PCK: " + ", ".join(leaked)
        )
    # Metadata becomes Godot-owned UID/import tables. Converted resources use remaps.
    missing = sorted(
        path
        for path in selected
        if not is_sidecar_named(path) and path not in ignored and not packed(path)
    )
    if missing:
        raise RuntimeError(
            "Godot omitted declared resources from the PCK: " + ", ".join(missing)
        )
    return {
        "packed_paths": sorted(paths),
        "selected_paths": sorted(selected),
        "excluded_paths": sorted(excluded),
        "pck_file_count": contents["file_count"],
    }


def content_selection(manifest: dict, execroot: Path) -> tuple[set[str], set[str]]:
    """Return the staged paths the pack's content file lists, and all others."""
    selected = set(
        json.loads((execroot / manifest["content"]).read_text(encoding="utf-8"))[
            "resources"
        ]
    )
    return selected, (
        manifest["member_resource_paths"].keys()
        | manifest.get("import_resource_paths", {}).keys()
    ) - selected


def write_report(
    report: Path,
    manifest: dict,
    selection: tuple[set[str], set[str]],
    paths: Collection[str],
    pck: Path,
    conversion: str,
) -> None:
    """
    Write a pack's .export.json report, checking its PCK's paths against its selection.

    Args:
        report: The report to write.
        manifest: The pack action's manifest, with its imports.
        selection: The selected and the excluded paths, from content_selection.
        paths: The PCK's paths.
        pck: The PCK.
        conversion: The pack form, "godot" or "none".
    """
    selected, excluded = selection
    contents = {"paths": sorted(paths), "file_count": len(paths)}
    report.write_text(
        json.dumps(
            {
                **inspect_export(
                    contents, selected, excluded, set(manifest.get("ignored_paths", []))
                ),
                "pack_conversion": conversion,
                "extension_library_paths": manifest.get("extension_library_paths", []),
                "engine_version": manifest["version"],
                "preset_platform": manifest["preset_platform"],
                "variant": manifest["variant"],
                "member_paths": sorted(manifest["member_resource_paths"]),
                "import_actions": len(manifest.get("imports", [])),
                "pck_sha256": digest(pck),
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
