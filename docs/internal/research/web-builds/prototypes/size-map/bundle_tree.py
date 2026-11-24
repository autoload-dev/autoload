"""
The whole web bundle's size tree for the size map: the engine's areas, the pack's files
by kind, the loader and the page.

Every leaf carries [as one HTML file, raw, brotli]. Engine leaves are bytes before
wasm-opt (`engine_tree.py`), scaled to the final wasm's raw and brotli sizes; pack files
are measured one by one. "As one HTML file" is raw plus base64 for binary files: the
naive single-file embedding, before `../playable/pack_playable.py` compresses it.

Usage: python3 bundle_tree.py <web export dir> <engine.json> <data.json>
"""

import importlib
import json
import re
import struct
import sys
from pathlib import Path

# Not a dependency of the repository: `pip install brotli`.
brotli = importlib.import_module("brotli")

BASE64 = 4 / 3
AREA_SLOTS = [
    "Rendering (GLES3, Shader)",
    "Variant & Kern",
    "Szene & UI",
    "Ressourcen & Dateien",
    "Start & Registrierung",
    "Text & Schriften",
    "GDScript",
    "Sonstiges",
]
KINDS = [
    ("Bilder (Texturen)", r"\.(ctex|png|webp|jpg)$"),
    ("Skript-Bytecode (.gdc)", r"\.gdc$"),
    ("Schrift", r"\.(fontdata|ttf|otf|woff2?)$|OFL\.txt$"),
    ("Szenen & Ressourcen", r"\.(tscn|tres|scn|res)$"),
    ("Import- & Projektdaten", r"."),
]
SHELL = [
    ("index.html", "HTML-Seite mit Startskript", False),
    ("index.audio.worklet.js", "Audio-Worklet", False),
    ("index.audio.position.worklet.js", "Audio-Positions-Worklet", False),
    ("index.png", "Startbild", True),
]


def compressed(data: bytes) -> int:
    return len(brotli.compress(data, quality=11))


def leaf(name: str, raw: float, br: float, binary: bool = True) -> dict:
    return {
        "n": name,
        "v": [round(raw * BASE64 if binary else raw), round(raw), round(br)],
    }


def group(name: str, kids: list[dict], slot: int | None = None) -> dict:
    return {"n": name, "c": kids} | ({"k": slot} if slot else {})


def pack_files(data: bytes) -> list[tuple[str, bytes]]:
    """(path, content) of every file in a Godot 4 pack (format 3)."""
    _, _, _, _, _, _, base, directory = struct.unpack_from("<4sIIIIIQQ", data, 0)
    (count,) = struct.unpack_from("<I", data, directory)
    pos, files = directory + 4, []
    for _ in range(count):
        (length,) = struct.unpack_from("<I", data, pos)
        path = data[pos + 4 : pos + 4 + length].rstrip(b"\0").decode()
        pos += 4 + length
        offset, size = struct.unpack_from("<QQ", data, pos)
        pos += 16 + 16 + 4  # Offset and size, MD5, flags.
        files.append((path, data[base + offset : base + offset + size]))
    return files


def pack_tree(pck: bytes) -> list[dict]:
    files = [
        (re.sub(r"-[0-9a-f]{32}(?=\.)", "", p), len(d), compressed(d))
        for p, d in pack_files(pck)
    ]
    kids, taken = [], set()
    for slot, (kind, pattern) in enumerate(KINDS, 1):
        mine = [f for f in files if re.search(pattern, f[0]) and f[0] not in taken]
        taken |= {f[0] for f in mine}
        mine.sort(key=lambda f: -f[1])
        leaves = [leaf(p, r, b) for p, r, b in mine if r >= 1000]
        small = [f for f in mine if f[1] < 1000]
        if small:
            leaves.append(
                leaf(
                    f"{len(small)} kleinere Dateien",
                    sum(f[1] for f in small),
                    sum(f[2] for f in small),
                )
            )
        kids.append(group(kind, leaves, slot))
    overhead = len(pck) - sum(f[1] for f in files)
    rest = max(0, compressed(pck) - sum(f[2] for f in files))
    kids.append(
        group(
            "Verzeichnis & Kopf",
            [leaf("Inhaltsverzeichnis des Packs", overhead, rest)],
            6,
        )
    )
    return kids


def engine_tree(engine: dict, wasm: bytes) -> tuple[list[dict], dict]:
    """The areas and the dominator tree, rescaled from bytes before wasm-opt."""
    scale_raw, scale_br = len(wasm) / engine["total"], compressed(wasm) / engine["total"]

    def rescale(n: dict) -> dict:
        if "c" in n:
            out = {"n": n["n"], "c": [rescale(c) for c in n["c"]]}
        else:
            out = leaf(n["n"], n["v"] * scale_raw, n["v"] * scale_br)
        if n.get("a") in AREA_SLOTS:
            out |= {"k": AREA_SLOTS.index(n["a"]) + 1, "a": n["a"]}
        return out

    return [rescale(a) for a in engine["areas"]["c"]], rescale(engine["dominators"])


def main() -> None:
    export, engine_json, out = map(Path, sys.argv[1:4])
    wasm = (export / "index.wasm").read_bytes()
    areas, dominators = engine_tree(json.loads(engine_json.read_text()), wasm)
    loader = (export / "index.js").read_bytes()
    shell = []
    for name, label, binary in SHELL:
        data = (export / name).read_bytes()
        shell.append(leaf(f"{label} ({name})", len(data), compressed(data), binary))
    bundle = group(
        "Alles",
        [
            group("Engine (index.wasm)", areas, 1),
            group(
                "Spieldaten (index.pck)",
                pack_tree((export / "index.pck").read_bytes()),
                2,
            ),
            group(
                "JS-Loader (index.js)",
                [
                    leaf(
                        "Emscripten-Loader und Godot-Web-API",
                        len(loader),
                        compressed(loader),
                        False,
                    )
                ],
                3,
            ),
            group("HTML & Kleinkram", shell, 4),
        ],
    )
    out.write_text(
        json.dumps({"bundle": bundle, "dominators": dominators}, ensure_ascii=False)
    )
    print(f"{out.stat().st_size:,} bytes of size map data")


if __name__ == "__main__":
    main()
