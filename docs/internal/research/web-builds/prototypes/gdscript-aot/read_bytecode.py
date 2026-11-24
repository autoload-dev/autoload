"""
Read the functions of precompiled GDScript bytecode (`gdscript_bytecode.cpp`, version 1):
for each, its script, class, name, code, names and function pointer tables.
"""

import importlib
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The stage A reader, next to this prototype.
sys.path.insert(0, str(Path(__file__).parents[1] / "gdscript-bytecode"))
bu = importlib.import_module("bytecode_usage")


@dataclass
class Function:
    script: str
    klass: str
    name: str
    code: list[int] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    tables: dict[str, list[str]] = field(default_factory=dict)
    lambdas: list[Function] = field(default_factory=list)


def _function(r: Any, script: str, klass: str) -> Function:
    name = r.text()
    r.text()
    r.u8()
    r.repeat(bu.data_type)
    bu.data_type(r)
    bu.variant(r)
    bu.variant(r)
    r.skip(5 * 4)
    n = r.u32()
    code = list(struct.unpack_from(f"<{n}i", r.data, r.pos))
    r.skip(4 * n)
    r.skip(4 * r.u32())
    r.repeat(bu.variant)
    r.repeat(lambda r: (r.text(), bu.variant(r)))
    f = Function(script, klass, name, code)
    f.names = [str(x) for x in r.repeat(bu.Reader.text)]
    for kind, read in bu._TABLES:
        entries = r.repeat(read)
        f.tables[kind or f"_{len(f.tables)}"] = [str(e) for e in entries]
    r.skip(8 * r.u32())
    for _ in range(r.u32()):
        r.skip(5)
        f.lambdas.append(_function(r, script, klass))
    return f


def _class(r: Any, script: str, out: list[Function]) -> None:
    klass = r.text()
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
        r.text()
        out.append(_function(r, script, klass))
        r.u8()
    for _ in range(3):
        if r.u8():
            out.append(_function(r, script, klass))


def functions(directory: Path) -> list[Function]:
    out: list[Function] = []
    for path in sorted(directory.rglob("*.gdc")):
        r = bu.Reader(path.read_bytes())
        r.skip(8)
        r.repeat(lambda r: (r.text(), r.text(), r.text()))
        for _ in range(r.u32()):
            _class(r, str(path.relative_to(directory)), out)
    return out


def flatten(fs: list[Function]) -> list[Function]:
    out = []
    for f in fs:
        out.append(f)
        out.extend(flatten(f.lambdas))
    return out
