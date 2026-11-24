"""
Pack a Godot web export into one HTML file for playable ads.

The engine (`index.wasm`), its loader (`index.js`) and the game's pack (`index.pck`)
are concatenated, compressed with LZMA and embedded as text, so no
part of the game is a separate request. A small decoder (`lzma.js`) and `boot.js`
unpack them in the page and answer the engine's `fetch()` calls from memory. Two text encodings: `base64` (accepted by every network) and `seven`, 7 bits per
byte of the page, for networks that allow base122-style payloads.

Prints the size every network counts: the HTML itself, and the HTML in a ZIP.

Usage: python3 pack_playable.py <web export dir> <output.html> [--encoding base64|seven]
"""

import base64
import io
import json
import lzma
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
# The audio worklets stay out: a build without threads mixes audio without them.
FILES = ("index.wasm", "index.pck", "index.js")
# Byte values the `seven` encoding writes as two-byte characters (see text_seven.js).
ILLEGAL = (0, 10, 13, 34, 38, 60, 92)
_LZMA = [
    {"id": lzma.FILTER_LZMA1, "preset": 9 | lzma.PRESET_EXTREME, "dict_size": 1 << 26}
]
_STYLE = (
    "html,body{margin:0;height:100%;overflow:hidden;background:#000}"
    "canvas{display:block;width:100%;height:100%;outline:none;touch-action:none}"
)


def seven(data: bytes) -> str:
    """The data as 7-bit characters, big-endian, zero-padded to whole characters."""
    data += bytes(-len(data) % 7)
    chunks = []
    for at in range(0, len(data), 7):
        block = int.from_bytes(data[at : at + 7], "big")
        chunks += [(block >> shift) & 127 for shift in range(49, -1, -7)]
    out = []
    it = iter(chunks)
    for c in it:
        if c in ILLEGAL:
            out.append(chr(256 + ILLEGAL.index(c) * 128 + next(it, 0)))
        else:
            out.append(chr(c))
    return "".join(out)


def script(name: str) -> str:
    """A script of this directory without comments and indentation."""
    lines = (line.strip() for line in (HERE / name).read_text().splitlines())
    return "\n".join(line for line in lines if line and not line.startswith("//"))


def page(export: Path, encoding: str) -> tuple[str, dict]:
    blobs = [(export / name).read_bytes() for name in FILES]
    raw = b"".join(blobs)
    packed = lzma.compress(raw, format=lzma.FORMAT_ALONE, filters=_LZMA)
    text = base64.b64encode(packed).decode() if encoding == "base64" else seven(packed)
    manifest = {
        "files": [[n, len(b)] for n, b in zip(FILES, blobs, strict=True)],
        "packed": len(packed),
        "total": len(raw),
    }
    code = "\n".join(
        [
            f"const PAYLOAD={json.dumps(manifest, separators=(',', ':'))};",
            script("lzma.js"),
            script(f"text_{encoding}.js"),
            script("boot.js"),
        ]
    )
    if re.search(r"</script", code, re.IGNORECASE):
        raise SystemExit("the boot code must not close its script element")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">'
        f"<title>Lichtpost</title><style>{_STYLE}</style></head><body>"
        '<canvas id="canvas"></canvas>'
        f'<script type="text/plain" id="payload">{text}</script>'
        f"<script>{code}</script></body></html>"
    )
    return html, {
        "raw": len(raw),
        "packed": len(packed),
        "text": len(text.encode()),
        "code": len(code),
    }


def zipped(html: bytes) -> int:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("index.html", html)
    return len(buffer.getvalue())


def main() -> None:
    export, output = Path(sys.argv[1]), Path(sys.argv[2])
    encoding = (
        sys.argv[sys.argv.index("--encoding") + 1]
        if "--encoding" in sys.argv
        else "base64"
    )
    html, sizes = page(export, encoding)
    data = html.encode()
    output.write_bytes(data)
    sizes |= {"html": len(data), "zip": zipped(data)}
    print(" ".join(f"{k} {v:,}" for k, v in sizes.items()))


if __name__ == "__main__":
    main()
