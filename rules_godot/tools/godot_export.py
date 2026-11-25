"""
Isolated Godot exports of packs and their applications' shell files.

The action manifest is the entire input set. The staging and editor runs are
shared with the project actions through godot_staging.py.

Sections: Export lock, Export presets, Pack assembly.
"""

import argparse
import contextlib
import fcntl
import json
import os
import re
import struct
import sys
from collections.abc import Collection, Iterator
from pathlib import Path
from typing import Any

from godot.private.project_config import validate_literal
from tools import template
from tools.godot_staging import (
    add_manifest_arguments,
    copy_file,
    extension_list,
    gd_string,
    join_action,
    load_manifest,
    run_action,
    staged_project,
)
from tools.pack_contents import (
    content_selection,
    excluded_with_sidecars,
    write_report,
)
from tools.pck import (
    EXTENSION_LIST,
    add_pck_files,
    engine_version,
    normalize_project_features,
    pck_file_contents,
    pck_file_member,
    pck_files,
    write_pck,
)

_ADAPTIVE_ICON = Path(__file__).parent / "adaptive_icon.xml.tpl"

# The image types of an Apple icon file that hold a PNG image of each size.
_ICNS_TYPES = {
    16: [b"icp4"],
    32: [b"icp5", b"ic11"],
    64: [b"ic12"],
    128: [b"ic07"],
    256: [b"ic08", b"ic13"],
    512: [b"ic09", b"ic14"],
    1024: [b"ic10"],
}


def icns(images: dict[int, bytes]) -> bytes:
    """Return an Apple icon file of PNG images by size."""
    entries = b"".join(
        kind + struct.pack(">I", len(data) + 8) + data
        for size, data in sorted(images.items(), reverse=True)
        for kind in _ICNS_TYPES[size]
    )
    return b"icns" + struct.pack(">I", len(entries) + 8) + entries


def _absolute(execroot: Path, source: str | list) -> str | list:
    """Return a probe image source with its image file's path absolute."""
    if isinstance(source, list):
        return [_absolute(execroot, part) for part in source]
    if source.startswith("file:"):
        return "file:" + str((execroot / source.removeprefix("file:")).absolute())
    return source


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


def export_presets(
    manifest: dict, excluded: Collection[str] = (), export_only: str = ""
) -> str:
    # Selection belongs to the project declaration. The only exclusion filter
    # passed to Godot is an expanded, inspectable list of declared paths, which
    # Godot reads as comma-separated glob patterns.
    excluded = sorted(excluded_with_sidecars(excluded))
    unfilterable = [
        path for path in excluded if any(character in path for character in "*,?[]")
    ]
    if unfilterable:
        raise ValueError(
            "Excluded resources cannot be literal export filter entries; they contain one of * , ? [ ]: "
            + ", ".join(unfilterable)
        )
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
        "EXCLUDE_FILTER": gd_string(",".join(excluded)),
        "OPTIONS": "\n".join(options),
    }
    return template.fill(_EXPORT_PRESETS, values)


def _export_nothing(manifest: dict, root: Path) -> None:
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


def shell_assets(manifest: dict, output: Path, execroot: Path) -> None:
    """
    Record what Godot decides for a pack's export and render its application images.

    The probe exports the staged project once more, without its files, and the
    export is thrown away: Godot reports the export options with their
    defaults, the project settings with the export's feature overrides and the
    version options' values, and renders the icons and splash images the
    specification lists into their outputs. An image whose source has a file
    type Godot uses as it is, such as a macOS .icns icon or an Android vector
    drawable, is copied instead.
    """
    spec = manifest["shell"]
    for directory in spec.get("directories", []):
        (execroot / directory).mkdir(parents=True, exist_ok=True)
    icns_output = execroot / spec["icns"] if "icns" in spec else None
    with staged_project(manifest, execroot, "godot-shell-") as (work, root, _):
        _export_nothing(manifest, root)
        images: list[dict[str, Any]] = [
            {
                **image,
                "sources": [_absolute(execroot, source) for source in image["sources"]],
                # Images without an output of their own go into the .icns file.
                "output": str(
                    (execroot / image["output"]).absolute()
                    if "output" in image
                    else work / "images" / (image["name"] + ".png")
                ),
            }
            | ({"copy": {"extension": ".icns"}} if icns_output else {})
            for image in spec["images"]
        ]
        join_action(
            root,
            work,
            "shell",
            {
                "images": images,
                "versions": spec["versions"],
                "option_names": spec.get("option_names", []),
                "authored_options": sorted(manifest.get("authored_export_options", {})),
            },
        )
        record = export_pack(manifest, execroot, root, work, work / "probe.pck")
        facts = record["facts"]
        if "rendered" not in facts:
            raise RuntimeError(
                "The shell probe recorded no export facts; its script failed:\n"
                + record["output"]
            )
        rendered = set(facts.pop("rendered"))
        copied: dict[str, str] = facts.pop("copied")
        for image in images:
            if image["name"] in copied:
                copy = image.get("copy", {}).get("output")
                destination = execroot / copy if copy else icns_output
                assert destination is not None
                if not destination.exists():
                    source = copied[image["name"]].removeprefix("res://")
                    copy_file(root / source, destination)
        missing = [
            i["name"] for i in images if i.get("required") and i["name"] not in rendered
        ]
        if missing:
            raise RuntimeError(
                "Godot rendered no image for " + ", ".join(missing) + "; the project "
                "or the export options name an image that does not load"
            )
        if icns_output and not icns_output.exists():
            sizes = {
                i["size"]: Path(i["output"]) for i in images if i["name"] in rendered
            }
            if sizes:
                # One .icns file holds the images, while the staging directory exists.
                icns_output.write_bytes(
                    icns({size: path.read_bytes() for size, path in sizes.items()})
                )
    adaptive = spec.get("adaptive_icon")
    if adaptive and adaptive["foreground"] in rendered:
        # Godot's adaptive icon names a monochrome layer only when it renders one.
        path = execroot / adaptive["output"]
        path.parent.mkdir(parents=True, exist_ok=True)
        monochrome = '    <monochrome android:drawable="@mipmap/icon_monochrome"/>'
        path.write_text(
            template.fill(
                _ADAPTIVE_ICON,
                {"MONOCHROME": monochrome if adaptive["monochrome"] in rendered else ""},
            ),
            encoding="utf-8",
        )
    output.write_text(
        json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


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


def configuration(manifest: dict, output: Path, report: Path, execroot: Path) -> None:
    """
    Export a pack's configuration: the PCK files a pack written without Godot needs from it.

    Godot exports the staged project without its files, as the shell probe does; the
    resulting project.binary depends on the project settings, the preset and the
    variant only, so content changes never rerun this. The output PCK holds that
    project.binary and the text server's support data where the runtime needs it:
    where Godot's export packed it, or where the project lists translations, whose
    locales Godot would read from files this export does not stage. The report holds
    the facts the writer needs: the export's feature tags and the settings naming
    files the runtime reads raw.
    """
    with staged_project(manifest, execroot, "godot-configuration-") as (work, root, _):
        _export_nothing(manifest, root)
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
        if name and (name in exported or facts["translations"]):
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=["check-options", "shell", "pack", "configuration"]
    )
    add_manifest_arguments(parser)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--facts", type=Path, help="Godot's facts, for check-options.")
    args = parser.parse_args()
    execroot = Path.cwd()
    manifest = load_manifest(args)
    output = args.output.absolute()
    if args.mode == "check-options":
        if args.facts is None:
            parser.error("check-options requires --facts")
        validate_export_facts(
            manifest, json.loads(args.facts.read_text(encoding="utf-8"))
        )
        output.write_text("checked\n", encoding="utf-8")
    elif args.mode == "shell":
        shell_assets(manifest, output, execroot)
    else:
        if args.report is None:
            parser.error(args.mode + " requires --report")
        run = configuration if args.mode == "configuration" else pack
        run(manifest, output, args.report.absolute(), execroot)


if __name__ == "__main__":
    main()
