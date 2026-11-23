"""
Attribute a wasm-ld map's CODE and DATA bytes to Godot source files.

Members of SCons archives are named by basename only; they are matched to sources by
basename within the archive's directory tree. Prints {"code": {path: bytes},
"data": {path: bytes}} as JSON.

Usage: python3 wasm_breakdown.py <link.map> <godot source> > breakdown.json
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

_SUFFIX = ".web.template_release.wasm32.nothreads"
_LINE = re.compile(r"^\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+(.*)$")
_MEMBER = re.compile(r"(.*)/lib[^/]*\.a\((.*)\)$")
_RUNTIME = "(emscripten runtime and libc)"


def source_index(source: Path) -> dict[str, list[str]]:
    """Return the source paths of each basename without extension."""
    index: dict[str, list[str]] = defaultdict(list)
    for root, _, files in os.walk(source):
        for name in files:
            if name.endswith((".cpp", ".c", ".cc", ".mm")):
                path = Path(root, name).relative_to(source)
                index[name.rsplit(".", 1)[0]].append(str(path))
    return index


def source_path(ref: str, index: dict[str, list[str]]) -> str:
    """Return the source path of a map input, or a label for non-engine input."""
    member = _MEMBER.match(ref)
    if member:
        base = member.group(2).replace(_SUFFIX + ".o", "").replace(".o", "")
        directory = member.group(1).replace("bin/obj/", "")
        candidates = index.get(base, [])
        picked = [c for c in candidates if c.startswith(directory)] or candidates
        return picked[0] if picked else directory + "/" + base
    if ref.startswith("bin/obj/"):
        path = ref.replace("bin/obj/", "").replace(_SUFFIX + ".o", "")
        return path if os.path.splitext(path)[1] else path + ".cpp"
    if "sysroot" in ref or ref.startswith("/") or "<internal>" in ref:
        return _RUNTIME
    return "(" + ref[:60] + ")"


def breakdown(lines: list[str], index: dict[str, list[str]]) -> dict[str, dict[str, int]]:
    """Return the CODE and DATA bytes of each source path."""
    section = None
    sizes: Counter[tuple[str, str]] = Counter()
    for line in lines:
        match = _LINE.match(line)
        if not match:
            continue
        rest = match.group(4).strip()
        if re.fullmatch(r"[A-Z_]+", rest):
            section = rest
            continue
        # The demangled line below each symbol repeats its size without an input.
        if section not in ("CODE", "DATA") or (
            ".o" not in rest and "<internal>" not in rest
        ):
            continue
        sizes[(section, source_path(rest.split(":(")[0], index))] += int(
            match.group(3), 16
        )
    result: dict[str, dict[str, int]] = {"code": {}, "data": {}}
    for (section_name, path), size in sizes.items():
        result["code" if section_name == "CODE" else "data"][path] = size
    return result


def main() -> None:
    lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
    json.dump(breakdown(lines, source_index(Path(sys.argv[2]))), sys.stdout)


if __name__ == "__main__":
    main()
