"""
List what precompiled GDScript bytecode uses from the engine.

Reads the `.gdc` files `dump_bytecode.gd` wrote (format of `gdscript_bytecode.cpp`,
version 1) and prints, as JSON, the method binds, built-in methods, utility functions,
operators and constructors the project's scripts call, and the names they call methods by:
the exact input for stripping the bindings nobody uses.

Usage: python3 bytecode_usage.py <bytecode dir> > usage.json
"""

import json
import struct
import sys
from collections.abc import Callable
from pathlib import Path


class Reader:
    """Sequential reader of the bytecode buffer."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def u8(self) -> int:
        self.pos += 1
        return self.data[self.pos - 1]

    def u32(self) -> int:
        (value,) = struct.unpack_from("<I", self.data, self.pos)
        self.pos += 4
        return value

    def text(self) -> str:
        length = self.u32()
        self.pos += length
        return self.data[self.pos - length : self.pos].decode()

    def skip(self, count: int) -> None:
        self.pos += count

    def repeat(self, read: Callable[[Reader], object]) -> list[object]:
        return [read(self) for _ in range(self.u32())]


def _object(r: Reader) -> None:
    if r.u8() != 0:
        r.text()


def _typed_container(r: Reader) -> None:
    r.u32()
    r.text()
    variant(r)


def _array(r: Reader) -> None:
    _typed_container(r)
    r.u8()
    r.repeat(variant)


def _dictionary(r: Reader) -> None:
    _typed_container(r)
    _typed_container(r)
    r.u8()
    r.repeat(lambda r: (variant(r), variant(r)))


_VARIANTS: dict[int, Callable[[Reader], None]] = {
    0: lambda r: r.skip(r.u32()),
    1: _object,
    2: _array,
    3: _dictionary,
}


def variant(r: Reader) -> None:
    _VARIANTS[r.u8()](r)


def data_type(r: Reader) -> None:
    r.u8()
    r.u32()
    r.text()
    r.text()
    r.u8()
    r.repeat(data_type)


def _type_name(r: Reader) -> str:
    return f"{r.u32()}.{r.text()}"


# The function's pointer tables in order: the usage they record, and how to read an entry.
_TABLES: list[tuple[str | None, Callable[[Reader], object]]] = [
    ("operators", lambda r: f"{r.u32()}:{r.u32()}:{r.u32()}"),
    ("setters", _type_name),
    ("getters", _type_name),
    (None, Reader.u32),
    (None, Reader.u32),
    (None, Reader.u32),
    (None, Reader.u32),
    ("builtin_methods", _type_name),
    ("constructors", lambda r: f"{r.u32()}#{r.u32()}"),
    ("utilities", Reader.text),
    ("gdscript_utilities", Reader.text),
    ("method_binds", lambda r: f"{r.text()}.{r.text()}"),
]


def _function_header(r: Reader) -> None:
    r.text()
    r.text()
    r.u8()
    r.repeat(data_type)
    data_type(r)
    variant(r)
    variant(r)
    r.skip(5 * 4)
    r.skip(4 * r.u32())
    r.skip(4 * r.u32())
    r.repeat(variant)
    r.repeat(lambda r: (r.text(), variant(r)))


def function(r: Reader, use: dict[str, set[str]]) -> None:
    _function_header(r)
    use["names"].update(str(name) for name in r.repeat(Reader.text))
    for kind, read in _TABLES:
        entries = r.repeat(read)
        if kind:
            use[kind].update(str(entry) for entry in entries)
    r.skip(8 * r.u32())
    for _ in range(r.u32()):
        r.skip(5)
        function(r, use)


def _member(r: Reader) -> None:
    r.text()
    r.u32()
    r.text()
    r.text()
    data_type(r)
    variant(r)


def _named_variant(r: Reader) -> None:
    r.text()
    variant(r)


def klass(r: Reader, use: dict[str, set[str]]) -> None:
    r.text()
    r.text()
    r.text()
    r.skip(2)
    use["native_bases"].add(r.text())
    r.text()
    r.repeat(_member)
    r.repeat(Reader.text)
    r.repeat(_member)
    r.repeat(_named_variant)
    r.repeat(_named_variant)
    variant(r)
    for _ in range(r.u32()):
        r.text()
        function(r, use)
        r.u8()
    for _ in range(3):
        if r.u8():
            function(r, use)


def main() -> None:
    use: dict[str, set[str]] = {kind: set() for kind, _ in _TABLES if kind}
    use["native_bases"] = set()
    use["names"] = set()
    for path in sorted(Path(sys.argv[1]).rglob("*.gdc")):
        r = Reader(path.read_bytes())
        r.skip(8)
        r.repeat(lambda r: (r.text(), r.text(), r.text()))
        for _ in range(r.u32()):
            klass(r, use)
    json.dump(
        {kind: sorted(values) for kind, values in use.items()}, sys.stdout, indent=1
    )


if __name__ == "__main__":
    main()
