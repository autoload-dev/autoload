"""
Isolated Godot project actions: imports, initialization and editor probes.

The action manifest is the entire input set. Exports are in godot_export.py and
the staging both share in godot_staging.py.

Sections: Import, Importers.
"""

import argparse
import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from tools.godot_staging import (
    ACTION_DIRECTORY,
    Original,
    add_manifest_arguments,
    copy_file,
    join_action,
    load_manifest,
    resource_path,
    run_action,
    same_content,
    staged_project,
    write_archive,
)
from tools.project.config import override_tags
from tools.resources.files import import_base, sidecars_of

# ==== Import ==================================================================


def _files(directory: Path) -> list[Path]:
    return (
        [source for source in directory.rglob("*") if source.is_file()]
        if directory.exists()
        else []
    )


# Staged files carry this modification time while Godot runs, so every file it
# writes stands out by a newer one: 2000-01-01, not 0, which Godot also reports
# for a file it cannot read.
_STAGED_TIME = 946684800


def _written_by_godot(
    relative: str, source: Path, originals: dict[str, Original]
) -> bool:
    """
    Whether Godot added or changed a staged project's file.

    Every file present before the run was staged and has an original. Only a file that
    Godot wrote, with a newer time, is compared with its original bytes.
    """
    if relative == "project.godot" or relative.startswith(ACTION_DIRECTORY + "/"):
        return False
    if relative not in originals:
        return True
    if source.stat().st_mtime_ns == _STAGED_TIME * 10**9:
        return False
    return not same_content(source, originals[relative])


def _import_changes(
    manifest: dict,
    execroot: Path,
    staged: tuple[Path, Path, dict[str, Original]],
    scope: Path,
) -> tuple[list[str], dict]:
    """
    Run Godot's import scan with the action plugin joined.

    The manifest's project file is already the import purpose's; staged is what
    staged_project yields: the work directory, project root and originals.

    Returns:
        The files below scope Godot added or changed, and Godot's record, whose
        facts list the files whose import Godot marked invalid.
    """
    work, root, originals = staged
    for source in _files(scope):
        os.utime(source, (_STAGED_TIME, _STAGED_TIME))
    record = run_action(manifest, execroot, root, work, ["--editor", "--import"])
    changed = []
    for source in _files(scope):
        relative = source.relative_to(root).as_posix()
        if _written_by_godot(relative, source, originals):
            changed.append(relative)
    return changed, record


def _fail_on_invalid(record: dict, required: set[str] | None = None) -> None:
    """Fail when Godot marked a required file's import invalid; None requires every file."""
    invalid = set(record["facts"]["invalid"])
    if required is not None:
        invalid &= required
    if invalid:
        raise RuntimeError(
            "Godot could not import "
            + ", ".join(sorted(invalid))
            + f"\nGodot's output:\n{record['output']}"
        )


def import_resources(manifest: dict, output: Path, execroot: Path) -> None:
    """Keep only this import unit's import results; global caches belong to the project."""
    with staged_project(manifest, execroot, "godot-import-") as staged:
        work, root, _ = staged
        join_action(root, work, "import")
        changed, record = _import_changes(
            manifest, execroot, staged, root / ".godot" / "imported"
        )
        # The importers the import stages are imported by their add-on's own imports.
        tools = tuple(import_base(path) for path in manifest.get("tools", []))
        changed = [relative for relative in changed if not relative.startswith(tools)]
        # Files of other units were imported, or failed, by their own actions.
        _fail_on_invalid(record, set(manifest["outputs"]))
        sidecars = [
            sidecar
            for relative in manifest["outputs"]
            for sidecar in sidecars_of(relative)
            if (root / sidecar).exists()
        ]
        write_archive(root, changed + sidecars, output)


# The caches Godot writes after its first scan, which source runs start from. Godot
# writes no UID cache for a project without resource UIDs; an absent one is empty, as
# for Godot itself, so only the script-class cache is required.
_EDITOR_CACHES = (".godot/global_script_class_cache.cfg",)


def initialize(manifest: dict, output: Path, execroot: Path) -> None:
    """
    Derive the editor state that source runs start from: Godot's global
    script-class and UID caches and anything its final scan adds.
    """
    with staged_project(manifest, execroot, "godot-initialize-") as staged:
        work, root, _ = staged
        join_action(root, work, "initialize")
        changed, record = _import_changes(manifest, execroot, staged, root)
        _fail_on_invalid(record)
        if record["stopped"]:
            # Godot was writing files when it was stopped; they would be cached.
            raise RuntimeError(
                "Godot did not exit after its initialization, so the editor state "
                f"it wrote may be incomplete:\n{record['output']}"
            )
        missing = [cache for cache in _EDITOR_CACHES if not (root / cache).exists()]
        if missing:
            raise RuntimeError("Godot did not write " + ", ".join(missing))
        output.mkdir(parents=True, exist_ok=True)
        for relative in changed:
            copy_file(root / relative, output / relative)


# ==== Importers ===============================================================


def _lowered(suffixes: Iterable[object]) -> set[str]:
    return {str(suffix).lower() for suffix in suffixes}


def _suffixes(record: dict) -> set[str]:
    return _lowered(record["facts"]["suffixes"])


def _editor_suffixes(manifest: dict, execroot: Path) -> set[str]:
    """The suffixes the editor recognizes with the manifest's files and plugins staged."""
    with staged_project(manifest, execroot, "godot-importers-") as (work, root, _):
        join_action(root, work, "importers")
        return _suffixes(
            run_action(manifest, execroot, root, work, ["--editor", "--quit"])
        )


def importer_mismatches(
    importers: list[dict], reported: dict[str, set[str]], built_in: set[str]
) -> list[str]:
    """
    Compare each add-on's declared importer suffixes with those its importers convert.

    Args:
        importers: The probed add-ons: label, declared suffixes and whether an extension
            of theirs may register importers (native).
        reported: The suffixes each add-on's importers convert, by label.
        built_in: The suffixes Godot imports without any add-on, which an extension's
            importer cannot be told apart from; a declared one of these is no mismatch
            for an add-on with an extension.

    Returns:
        One message per suffix that differs, naming the add-on and the suffix.
    """
    messages = []
    for importer in importers:
        label = importer["label"]
        declared = set(importer["suffixes"])
        found = reported.get(label, set())
        for suffix in sorted(found - declared):
            messages.append(
                f"{label} registers an importer for the suffix {suffix!r}, "
                "which its importer_suffixes do not declare"
            )
        unconfirmed = built_in if importer["native"] else set()
        for suffix in sorted(declared - found - unconfirmed):
            messages.append(
                f"{label} declares the importer suffix {suffix!r}, "
                "which none of its importers converts"
            )
    return messages


def _probe_importers(
    manifest: dict, execroot: Path, importers: list[dict]
) -> tuple[dict, dict]:
    """Run the editor and the runtime with the importers staged; return their records."""
    with staged_project(manifest, execroot, "godot-importers-") as (work, root, _):
        join_action(
            root,
            work,
            "importers",
            {"importer_scripts": {each["label"]: each["scripts"] for each in importers}},
        )
        editor = run_action(manifest, execroot, root, work, ["--editor", "--quit"])
        runtime = run_action(
            manifest,
            execroot,
            root,
            work,
            ["--script", f"res://{ACTION_DIRECTORY}/runtime.gd"],
        )
    return editor, runtime


def _native_suffixes(
    manifest: dict, execroot: Path, native: list[dict]
) -> tuple[dict[str, set[str]], set[str]]:
    """
    The suffixes the editor recognizes only with each add-on with an extension staged.

    Returns:
        Those suffixes by add-on label, and the suffixes the editor recognizes with no
        add-on, which an extension's importer cannot be told apart from; both empty
        without such add-ons.
    """
    if not native:
        return {}, set()
    alone = {"member_resource_paths": {}, "editor_plugins": [], "imports": []}
    built_in = _editor_suffixes(manifest | alone, execroot)
    added = {}
    for each in native:
        with_addon = _editor_suffixes(
            manifest
            | alone
            | {
                "member_resource_paths": each["member_resource_paths"],
                "editor_plugins": [each["plugin"]] if each["plugin"] else [],
            },
            execroot,
        )
        added[each["label"]] = with_addon - built_in
    return added, built_in


def importable_suffixes(manifest: dict, output: Path, execroot: Path) -> None:
    """
    Record the file suffixes Godot's importers handle in this import context.

    Importers exist only in the editor, so the suffixes its resource loaders
    recognize minus those recognized at runtime are exactly the importable ones.
    Each becomes an empty file in output, a listing Bazel can expand.

    The probe stages and enables the importers of the add-ons the project names and
    checks each add-on's declared suffixes against what its importers convert. Godot
    lists no importer with its owner: the script importers of an add-on are those of
    its editor-part scripts, found by reflection, and an add-on with an extension
    contributes the suffixes the editor recognizes only with that add-on staged.
    """
    importers = manifest.get("importers", [])
    editor, runtime = _probe_importers(manifest, execroot, importers)
    reported: dict[str, set[str]] = {each["label"]: set() for each in importers}
    for found in editor["facts"].get("importers", []):
        reported[found["label"]].update(_lowered(found["suffixes"]))
    added, built_in = _native_suffixes(
        manifest, execroot, [each for each in importers if each["native"]]
    )
    for label, suffixes in added.items():
        reported[label].update(suffixes)
    mismatches = importer_mismatches(importers, reported, built_in)
    if mismatches:
        raise RuntimeError(
            "The importers Godot reports differ from the declared importer suffixes:\n"
            + "\n".join(mismatches)
        )
    output.mkdir(parents=True, exist_ok=True)
    for suffix in sorted(_suffixes(editor) - _suffixes(runtime)):
        (output / resource_path(suffix)).touch()


def import_features(manifest: dict, output: Path, execroot: Path) -> None:
    """
    Record which feature tags of the project's overrides the editor of import actions has.

    A project without feature overrides needs no Godot process.
    """
    base = (execroot / manifest["project_file"]).read_text(encoding="utf-8")
    tags = override_tags(base, manifest.get("setting_keys", []))
    active: dict[str, bool] = {}
    if tags:
        # The editor's features do not depend on the project's files.
        with tempfile.TemporaryDirectory(prefix="godot-features-") as temporary:
            work = Path(temporary)
            root = work / "project"
            root.mkdir()
            (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
            join_action(root, work, "features", {"tags": tags})
            active = run_action(manifest, execroot, root, work, ["--editor", "--quit"])[
                "facts"
            ]
    output.write_text(json.dumps(active, sort_keys=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["suffixes", "features", "import", "initialize"])
    add_manifest_arguments(parser)
    args = parser.parse_args()
    execroot = Path.cwd()
    manifest = load_manifest(args)
    output = args.output.absolute()
    if args.mode == "suffixes":
        importable_suffixes(manifest, output, execroot)
    elif args.mode == "features":
        import_features(manifest, output, execroot)
    elif args.mode == "import":
        import_resources(manifest, output, execroot)
    else:
        initialize(manifest, output, execroot)


if __name__ == "__main__":
    main()
