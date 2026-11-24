"""
Strip the bodies of compiled functions from GDScript bytecode.

A function compiled to C++ never runs its bytecode, but the loader still builds the
function from it: its name, argument and return types, argument count and the table of
default arguments, whose length sets how many arguments a caller may leave out. This
keeps that head and writes the code, constants, global names and pointer tables of every
compiled function (`gen_cpp.py`'s usage, `compiled`) as empty.

Usage: python3 strip_bytecode.py <bytecode dir> <gen_cpp usage.json> <output dir>
"""

import importlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "gdscript-bytecode"))
# The bytecode reader of the sibling prototype.
bu = importlib.import_module("bytecode_usage")

_EMPTY = struct.pack("<I", 0)
# The pointer tables after the global names: eleven, then the method binds.
_TABLES = [read for _, read in bu._TABLES]


class _Stripper:
    def __init__(self, data: bytes, compiled: set[str]) -> None:
        self.r = bu.Reader(data)
        self.compiled = compiled
        self.out = bytearray()
        self.last = 0
        self.stripped = 0

    def copy_to(self, pos: int) -> None:
        self.out += self.r.data[self.last : pos]
        self.last = pos

    def body(self) -> None:
        """At a compiled function: keep its head, empty the rest."""
        r = self.r
        r.text()
        r.text()
        r.u8()
        r.repeat(bu.data_type)
        bu.data_type(r)
        bu.variant(r)
        bu.variant(r)
        r.skip(5 * 4)
        self.copy_to(r.pos)
        r.skip(4 * r.u32())  # Code.
        self.out += _EMPTY
        self.last = r.pos
        r.skip(4 * r.u32())  # Default arguments: kept.
        self.copy_to(r.pos)
        r.repeat(bu.variant)  # Constants.
        self.out += _EMPTY
        self.last = r.pos
        r.repeat(lambda r: (r.text(), bu.variant(r)))  # Local constants: kept.
        self.copy_to(r.pos)
        r.repeat(bu.Reader.text)
        for read in _TABLES:
            r.repeat(read)
        r.skip(8 * r.u32())  # Temporary slots.
        if r.u32():
            raise SystemExit("compiled functions with lambdas are not supported")
        self.out += _EMPTY * (1 + len(_TABLES) + 1 + 1)
        self.last = r.pos
        self.stripped += 1

    def function(self, fqcn: str, name: str) -> None:
        if f"{fqcn}.{name}" in self.compiled:
            self.body()
        else:
            bu.function(self.r, bu._discard())

    def klass(self) -> None:
        r = self.r
        fqcn = r.text()
        r.text()
        r.text()
        r.skip(2)
        r.text()
        r.text()
        r.repeat(bu._member)
        r.repeat(bu.Reader.text)
        r.repeat(bu._member)
        r.repeat(bu._named_variant)
        r.repeat(bu._named_variant)
        bu.variant(r)
        for _ in range(r.u32()):
            self.function(fqcn, r.text())
            r.u8()
        for name in ("@implicit_new", "@implicit_ready", "@static_initializer"):
            if r.u8():
                self.function(fqcn, name)

    def strip(self) -> bytes:
        r = self.r
        r.skip(8)
        r.repeat(lambda r: (r.text(), r.text(), r.text()))
        for _ in range(r.u32()):
            self.klass()
        self.copy_to(len(r.data))
        return bytes(self.out)


def main() -> None:
    source, usage, destination = map(Path, sys.argv[1:4])
    compiled = set(json.loads(usage.read_text())["compiled"])
    total = 0
    for path in sorted(source.rglob("*.gdc")):
        stripper = _Stripper(path.read_bytes(), compiled)
        out = destination / path.relative_to(source)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(stripper.strip())
        total += stripper.stripped
    print(f"{total} function bodies stripped")


if __name__ == "__main__":
    main()
