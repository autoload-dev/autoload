"""
Write a PCK whose scripts are replaced by precompiled bytecode.

Each `x.gd` becomes `x.gdc`, the bytecode `dump_bytecode.gd` wrote, and `x.gd.remap`, the
remap Godot's export writes for binary tokens, so scenes keep referring to `x.gd`.

Usage: python3 bytecode_pck.py <source.pck> <bytecode dir> <destination.pck> <rules_godot/tools>
"""

import importlib
import sys
from pathlib import Path


def main() -> None:
    source, bytecode_dir, destination, tools = sys.argv[1:5]
    sys.path.insert(0, tools)
    pck = importlib.import_module("pck")
    files = pck.pck_files(source)
    out = {}
    for path, data in files.items():
        if path.endswith(".gd"):
            gdc = path[:-3] + ".gdc"
            out[gdc] = (Path(bytecode_dir) / gdc).read_bytes()
            out[path + ".remap"] = f'[remap]\n\npath="res://{gdc}"\n'.encode()
        else:
            out[path] = data
    pck.write_pck(destination, out, (4, 7, 2))
    print(f"{len(files)} entries in, {len(out)} out")


if __name__ == "__main__":
    main()
