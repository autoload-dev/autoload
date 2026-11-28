"""
The shell probe: the export facts and application images of a pack's shell files.

The probe runs the pack's export once more without the project's files. It builds on
export.py's export of a placeholder.
"""

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools import template
from tools.editor_action.action import join_action
from tools.editor_action.export import export_nothing, export_pack
from tools.inputs.originals import copy_file
from tools.staging.project import staged_project

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


@dataclass(frozen=True)
class _ShellOutputs:
    """Where the shell probe's images go, rendered by Godot or used as they are."""

    execroot: Path
    work: Path
    # The macOS .icns file. It holds the images that have no output of their own.
    icns: Path | None

    def probe_image(self, image: dict) -> dict[str, Any]:
        """An image of the specification as the probe's script reads it, with absolute paths."""
        return {
            **image,
            "sources": [_absolute(self.execroot, source) for source in image["sources"]],
            # Images without an output of their own go into the .icns file.
            "output": str(
                (self.execroot / image["output"]).absolute()
                if "output" in image
                else self.work / "images" / (image["name"] + ".png")
            ),
        } | ({"copy": {"extension": ".icns"}} if self.icns else {})

    def copy_destination(self, image: dict) -> Path:
        """
        Where to copy a file that Godot uses as it is.

        That is the image's copy output, else the .icns file.
        """
        copy = image.get("copy", {}).get("output")
        destination = self.execroot / copy if copy else self.icns
        assert destination is not None
        return destination


def _copy_used_files(
    images: list[dict], copied: dict[str, str], root: Path, outputs: _ShellOutputs
) -> None:
    """Copy the staged files that Godot uses as images as they are, by image name."""
    for image in images:
        if image["name"] in copied:
            destination = outputs.copy_destination(image)
            if not destination.exists():
                source = copied[image["name"]].removeprefix("res://")
                copy_file(root / source, destination)


def _require_rendered(images: list[dict], rendered: set[str]) -> None:
    missing = [
        i["name"] for i in images if i.get("required") and i["name"] not in rendered
    ]
    if missing:
        raise RuntimeError(
            "Godot rendered no image for " + ", ".join(missing) + "; the project "
            "or the export options name an image that does not load"
        )


def _write_icns(path: Path | None, images: list[dict], rendered: set[str]) -> None:
    """Write the .icns file of the rendered images, unless Godot copied one or rendered none."""
    if path is None or path.exists():
        return
    sizes = {i["size"]: Path(i["output"]) for i in images if i["name"] in rendered}
    if sizes:
        path.write_bytes(icns({size: png.read_bytes() for size, png in sizes.items()}))


_ADAPTIVE_ICON = Path(__file__).parent / "adaptive_icon.xml.tpl"


def _write_adaptive_icon(
    adaptive: dict | None, rendered: set[str], execroot: Path
) -> None:
    """Write the Android adaptive icon the specification names, if Godot rendered its foreground."""
    if not adaptive or adaptive["foreground"] not in rendered:
        return
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


def shell_assets(manifest: dict, output: Path, execroot: Path) -> None:
    """
    Record what Godot decides for a pack's export and render its application images.

    The probe exports the staged project once more, without its files, and throws
    the export away. Godot reports the export options with their defaults, and the
    project settings with the export's feature overrides and the version options'
    values. It renders the icons and splash images that the specification lists into
    their outputs. An image whose source Godot uses as it is, such as a macOS .icns
    icon or an Android vector drawable, is copied instead.
    """
    spec = manifest["shell"]
    for directory in spec.get("directories", []):
        (execroot / directory).mkdir(parents=True, exist_ok=True)
    icns_output = execroot / spec["icns"] if "icns" in spec else None
    with staged_project(manifest, execroot, "godot-shell-") as (work, root, _):
        export_nothing(manifest, root)
        outputs = _ShellOutputs(execroot, work, icns_output)
        images = [outputs.probe_image(image) for image in spec["images"]]
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
        _copy_used_files(images, facts.pop("copied"), root, outputs)
        _require_rendered(images, rendered)
        # The .icns file packs rendered images from the staging directory, so the
        # export writes it before that directory goes away.
        _write_icns(icns_output, images, rendered)
    _write_adaptive_icon(spec.get("adaptive_icon"), rendered, execroot)
    output.write_text(
        json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
