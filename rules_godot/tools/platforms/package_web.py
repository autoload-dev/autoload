"""
PROTOTYPE(web): assemble a Godot web export from a web template ZIP and a PCK.

Mirrors what EditorExportPlatformWeb::export_project and _fix_html do for a plain
export: rename the template's godot.* files after the export's name, add the PCK, and
fill the HTML shell's $GODOT_* placeholders from the export options and project
settings the pack's facts record. The PWA files and the rendered icons are left out.
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

# The export's base name: Godot names every file after the exported HTML file.
NAME = "index"

# The template members a no-threads, no-dlink web template has, besides the HTML shell.
_COPIED = (
    "godot.js",
    "godot.wasm",
    "godot.audio.worklet.js",
    "godot.audio.position.worklet.js",
)


def _option(facts: dict, name: str, default: Any) -> Any:
    return facts.get("options", {}).get(name, default)


def _setting(facts: dict, name: str, default: Any) -> Any:
    return facts.get("settings", {}).get(name, default)


def _godot_bool(value: object) -> str:
    return "true" if value in (True, "true", 1) else "false"


def _color_html(value: object) -> str:
    """#rrggbb of a Godot Color, as Color.to_html(false); the facts carry it as a string or list."""
    if isinstance(value, str) and value.startswith("Color("):
        parts = [float(part) for part in value[len("Color(") : -1].split(",")]
    elif isinstance(value, (list, tuple)):
        parts = [float(part) for part in value]
    else:
        return "#000000"
    return "#" + "".join(
        f"{round(max(0.0, min(1.0, part)) * 255):02x}" for part in parts[:3]
    )


def _html(template: str, facts: dict, file_sizes: dict[str, int], threads: bool) -> str:
    config = {
        "args": [],
        "canvasResizePolicy": int(_option(facts, "html/canvas_resize_policy", 2)),
        "ensureCrossOriginIsolationHeaders": _option(
            facts, "progressive_web_app/ensure_cross_origin_isolation_headers", True
        )
        in (True, "true"),
        "executable": NAME,
        "experimentalVK": _option(facts, "html/experimental_virtual_keyboard", False)
        in (True, "true"),
        "fileSizes": file_sizes,
        "focusCanvas": _option(facts, "html/focus_canvas_on_start", True)
        in (True, "true"),
        "gdextensionLibs": [],
    }
    replacements = {
        "$GODOT_URL": NAME + ".js",
        "$GODOT_PROJECT_NAME": str(_setting(facts, "application/config/name", "")),
        "$GODOT_HEAD_INCLUDE": str(_option(facts, "html/head_include", "")),
        "$GODOT_CONFIG": json.dumps(config, sort_keys=True),
        "$GODOT_SPLASH_COLOR": _color_html(
            _setting(facts, "application/boot_splash/bg_color", None)
        ),
        "$GODOT_SPLASH_CLASSES": " ".join(
            f"{css}--{_godot_bool(_setting(facts, setting, default))}"
            for css, setting, default in (
                ("show-image", "application/boot_splash/show_image", True),
                ("fullsize", "application/boot_splash/fullsize", True),
                ("use-filter", "application/boot_splash/use_filter", True),
            )
        ),
        "$GODOT_SPLASH": NAME + ".png",
        "$GODOT_THREADS_ENABLED": "true" if threads else "false",
    }
    # Longer placeholders first, as $GODOT_SPLASH prefixes $GODOT_SPLASH_COLOR.
    for key in sorted(replacements, key=len, reverse=True):
        template = template.replace(key, replacements[key])
    return template


def _archive(site: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path in sorted(site.rglob("*")):
            info = zipfile.ZipInfo(
                path.relative_to(site).as_posix(), date_time=(1980, 1, 1, 0, 0, 0)
            )
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(info, path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--splash", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()

    facts = json.loads(args.facts.read_text())
    site: Path = args.output
    site.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.template) as template:
        members = set(template.namelist())
        threads = (
            "godot.worker.js" in members
        )  # Not in 4.3+; threads come from the template's build.
        for member in _COPIED:
            (site / member.replace("godot.", NAME + ".", 1)).write_bytes(
                template.read(member)
            )
        html = template.read("godot.html").decode()
    shutil.copyfile(args.pack, site / (NAME + ".pck"))
    shutil.copyfile(args.splash, site / (NAME + ".png"))
    file_sizes = {
        NAME + ".pck": (site / (NAME + ".pck")).stat().st_size,
        NAME + ".wasm": (site / (NAME + ".wasm")).stat().st_size,
    }
    (site / (NAME + ".html")).write_text(_html(html, facts, file_sizes, threads))
    _archive(site, args.archive)


if __name__ == "__main__":
    main()
