"""
Isolated Godot exports of packs and of their configuration.

The action manifest is the entire input set. The staging and editor runs are
shared with the project actions through tools/staging and action.py. The shell
probe in shell_assets.py builds on the export of a placeholder.

Sections: Export lock, Export presets, Pack assembly.
"""

import contextlib
import fcntl
import json
import os
import re
import sys
from collections.abc import Collection, Iterator
from pathlib import Path

from tools import template
from tools.editor_action.action import join_action, run_action
from tools.pack.contents import (
    content_selection,
    excluded_with_sidecars,
    write_report,
)
from tools.pack.pck import (
    add_pck_files,
    engine_version,
    normalize_project_features,
    pck_file_contents,
    pck_file_member,
    pck_files,
    write_pck,
)
from tools.project.config import validate_literal
from tools.resources.files import EXTENSION_LIST
from tools.resources.text import gd_string
from tools.staging.files import extension_list
from tools.staging.project import staged_project

# ==== Export lock =============================================================


# <unistd.h>'s confstr name for the user's temporary directory; Python's os module
# has no symbolic name for it.
_CS_DARWIN_USER_TEMP_DIR = 65537


def export_lock() -> Path | None:
    """Return the lock file of exports that share a temporary directory, if any."""
    directory = os.confstr(_CS_DARWIN_USER_TEMP_DIR) if sys.platform == "darwin" else None
    return Path(directory) / "rules_godot-export.lock" if directory else None


@contextlib.contextmanager
def exclusive_export() -> Iterator[None]:
    """
    Serialize exports that share Godot's temporary project.binary.

    Godot writes every export's configuration to tmpproject.binary in the
    operating system's temporary directory. On macOS that is the user's
    directory, whatever TMPDIR says, so concurrent exports would overwrite and
    delete each other's file.
    """
    path = export_lock()
    if path is None:
        yield
        return
    with path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def export_pack(
    manifest: dict, execroot: Path, root: Path, work: Path, output: Path
) -> dict:
    """
    Export the staged project's pack, as the editor exports the pack's variant.

    The action plugin must have joined the project; returns its record.
    """
    # --export-debug alongside --export-pack exports the pack with the debug
    # template's features, as the editor's debug export does.
    debug_arguments = (
        ["--export-debug", "Bazel"] if manifest["variant"] == "debug" else []
    )
    with exclusive_export():
        return run_action(
            manifest,
            execroot,
            root,
            work,
            [*debug_arguments, "--export-pack", "Bazel", str(output)],
        )


# ==== Export presets ==========================================================


_EXPORT_PRESETS = Path(__file__).parent / "export_presets.cfg.tpl"

# Godot exports at least one file; the shell probe skips it.
_SHELL_RESOURCE = "rules_godot_shell.tres"

# The one message Godot prints when the export loads a scene or resource of a class it does
# not know. The export then drops values of that class, such as a sub-resource, and still
# succeeds, so this message is the only report of the loss (research D28).
_UNKNOWN_CLASS = re.compile(r"Cannot get class '([^']+)'")


def require_known_classes(output: str, owner: str) -> None:
    """
    Fail an export during which Godot met a class it does not know.

    The export loads every extension of the pack, so a class is unknown when its
    extension is missing from the pack's deps or has no library for the platform that
    runs the export (#166).

    Args:
        output: What Godot printed during the export.
        owner: Label of the pack, for the message.
    """
    classes = sorted(set(_UNKNOWN_CLASS.findall(output)))
    if not classes:
        return
    them = "it" if len(classes) == 1 else "them"
    hint = (
        f"Add the extension that registers {them} to the pack's deps, or give that "
        "extension a library for the platform that runs the export."
    )
    raise RuntimeError(
        f"{owner}: Godot did not know the class "
        + ", ".join(classes)
        + " during the export, which drops values of an unknown class from the scenes "
        "and resources it converts. " + hint
    )


def validate_export_facts(manifest: dict, facts: dict) -> None:
    """
    Validate authored options against the exporter's live registration and types.

    Analysis has already rejected the options rules_godot owns or does not support.
    """
    for key in manifest.get("authored_export_options", {}):
        if key not in facts["options"] or key not in facts["option_types"]:
            raise ValueError(
                f"Export option {key} is not registered by this Godot exporter or an extension's export plugin"
            )
        expected = facts["option_types"][key]
        actual = facts.get("actual_option_types", {}).get(key)
        if actual is None:
            value = facts["options"][key]
            actual = {
                bool: "bool",
                int: "int",
                float: "float",
                str: "String",
                list: "Array",
                dict: "Dictionary",
            }.get(type(value), "Nil")
        if expected != actual:
            raise ValueError(
                f"Export option {key} requires Godot {expected}, got {actual}"
            )


def _exclude_filter(excluded: Collection[str]) -> str:
    """The exclude filter of the preset: the excluded paths with their sidecars."""
    # The project declaration selects the files. Godot gets one exclude filter only:
    # the declared paths, listed one by one, which it reads as comma-separated glob
    # patterns.
    paths = sorted(excluded_with_sidecars(excluded))
    unfilterable = [
        path for path in paths if any(character in path for character in "*,?[]")
    ]
    if unfilterable:
        raise ValueError(
            "Excluded resources cannot be literal export filter entries; they contain one of * , ? [ ]: "
            + ", ".join(unfilterable)
        )
    return ",".join(paths)


def _preset_fields(manifest: dict) -> list[str]:
    """The preset's fields: its custom features and an authored script export mode."""
    # godot_pack validates the preset fields and option names at analysis.
    authored = manifest.get("preset_settings", {})
    fields = []
    features = list(dict.fromkeys(manifest.get("features", [])))
    if features:
        fields.append("custom_features=" + gd_string(",".join(features)))
    if "script_export_mode" in authored:
        fields.append(
            "script_export_mode=" + validate_literal(authored["script_export_mode"])
        )
    return fields


def export_presets(
    manifest: dict, excluded: Collection[str] = (), export_only: str = ""
) -> str:
    exclude_filter = _exclude_filter(excluded)
    fields = _preset_fields(manifest)
    options = [
        f"{key}={validate_literal(value)}"
        for layer in ["preset_prelude", "export_options"]
        for key, value in sorted(manifest.get(layer, {}).items())
    ]
    values = {
        # A preset of one selected resource exports only that resource.
        "EXPORT_FILTER": gd_string("resources" if export_only else "all_resources"),
        "INCLUDE_FILTER": gd_string("" if export_only else "*"),
        "EXPORT_FILES": (
            f"export_files=PackedStringArray({gd_string(export_only)})"
            if export_only
            else ""
        ),
        "PLATFORM": gd_string(manifest["preset_platform"]),
        "PRESET_SETTINGS": "\n".join(fields),
        "EXCLUDE_FILTER": gd_string(exclude_filter),
        "OPTIONS": "\n".join(options),
    }
    return template.fill(_EXPORT_PRESETS, values)


def export_nothing(manifest: dict, root: Path) -> None:
    """Let the staged project's export pack only a placeholder, as a probe of the export."""
    if (root / _SHELL_RESOURCE).exists():
        raise ValueError(f"res://{_SHELL_RESOURCE} is reserved for rules_godot")
    (root / _SHELL_RESOURCE).write_text(
        '[gd_resource type="Resource" format=3]\n', encoding="utf-8"
    )
    (root / "export_presets.cfg").write_text(
        export_presets(manifest, export_only=f"res://{_SHELL_RESOURCE}"),
        encoding="utf-8",
    )


# ==== Pack assembly ===========================================================


def validate_pck(path: Path) -> dict:
    """Return the directory of a PCK; Godot can exit 0 after a failed export."""
    try:
        contents = pck_file_contents(path, include_paths=True)
    except (OSError, ValueError) as error:
        raise RuntimeError(
            f"Godot did not produce a valid Godot 4.7.2+ PCK v4: {error}"
        ) from error
    if path.stat().st_size < 100:
        raise RuntimeError("Godot produced an empty PCK")
    return contents


def _needs_support_data(name: str, exported: dict[str, bytes], facts: dict) -> bool:
    """Whether the configuration holds the text server's support data of that name."""
    if not name:
        return False
    return name in exported or bool(facts["translations"])


def configuration(manifest: dict, output: Path, report: Path, execroot: Path) -> None:
    """
    Export a pack's configuration: the PCK files a pack written without Godot needs from it.

    Godot exports the staged project without its files, as the shell probe does. The
    resulting project.binary depends only on the project settings, the preset and the
    variant, so content changes never rerun this export. The output PCK holds that
    project.binary and, where the runtime needs it, the text server's support data:
    where Godot's export packed it, or where the project lists translations. Godot
    would read their locales from files that this export does not stage. The report
    holds the facts the writer needs: the export's feature tags and the settings that
    name files the runtime reads raw.
    """
    with staged_project(manifest, execroot, "godot-configuration-") as (work, root, _):
        export_nothing(manifest, root)
        support_data = work / "support_data"
        join_action(root, work, "configuration", {"support_data": str(support_data)})
        probe = work / "configuration.pck"
        record = export_pack(manifest, execroot, root, work, probe)
        facts = record["facts"]
        if "features" not in facts:
            raise RuntimeError(
                "The configuration export recorded no facts; its script failed:\n"
                + record["output"]
            )
        validate_pck(probe)
        exported = pck_files(probe)
        synthesized = set(manifest.get("synthesized_cpu_features", []))
        files = {
            "project.binary": normalize_project_features(
                exported["project.binary"], synthesized
            )
        }
        name = facts.pop("support_data", "")
        if _needs_support_data(name, exported, facts):
            files[name] = exported.get(name) or support_data.read_bytes()
        write_pck(output, files, engine_version(manifest["version"]))
    report.write_text(
        json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def runtime_descriptors(
    execroot: Path, exported: Path, descriptors: dict[str, str]
) -> dict[str, bytes]:
    """
    Return the PCK entries that put the extensions' runtime descriptors in place.

    The export's editor loads the extension editor libraries, whose descriptors
    Godot packed. Godot lists only the extensions its editor loaded; the runtime
    loads those disabled for the export as well.
    """
    files = {
        path: (execroot / source).read_bytes() for path, source in descriptors.items()
    }
    listed = pck_file_contents(exported)["extension_list"]
    files[EXTENSION_LIST] = extension_list(
        {*(path.removeprefix("res://") for path in listed), *descriptors}
    )
    return files


def pack(manifest: dict, output: Path, report: Path, execroot: Path) -> None:
    selected, excluded = content_selection(manifest, execroot)
    with staged_project(manifest, execroot, "godot-pack-") as (work, root, _):
        (root / "export_presets.cfg").write_text(
            export_presets(manifest, excluded), encoding="utf-8"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptors = {
            path: source
            for path, source in manifest.get("runtime_descriptors", {}).items()
            if path in selected
        }
        synthesized = set(manifest.get("synthesized_cpu_features", []))
        exported = work / "export.pck" if descriptors or synthesized else output
        # The export scans and imports the staged project itself; a separate
        # import launch would start the editor a second time for no other output.
        join_action(root, work, "export")
        record = export_pack(manifest, execroot, root, work, exported)
        require_known_classes(record.get("output", ""), manifest["owner"])
        files = (
            runtime_descriptors(execroot, exported, descriptors) if descriptors else {}
        )
        if synthesized:
            files["project.binary"] = normalize_project_features(
                pck_file_member(exported, "project.binary"), synthesized
            )
        if files:
            add_pck_files(exported, output, files)
        write_report(
            report,
            manifest,
            (selected, excluded),
            validate_pck(output)["paths"],
            output,
            "godot",
        )
