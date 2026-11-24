"""
Read a relocatable WebAssembly object (such as wasm-ld's `--save-temps` LTO output): its
symbols with sizes and the references between them, from the `linking` and `reloc.*`
custom sections.

A reference is an edge from the symbol whose bytes hold a relocation (a function body or
a data symbol) to the symbol the relocation names: calls, taken function addresses (table
indices), and data addresses.
"""

import bisect
from dataclasses import dataclass, field
from pathlib import Path

_FUNCTION, _DATA, _GLOBAL, _SECTION, _TAG, _TABLE = range(6)
_UNDEFINED, _EXPORTED, _EXPLICIT_NAME, _NO_STRIP = 0x10, 0x20, 0x40, 0x80
# Relocation types that carry an addend.
_ADDEND = {3, 4, 5, 8, 9, 11, 14, 15, 16, 17, 21, 22, 23, 25}
_SYMBOL_TABLE, _SEGMENT_INFO, _INIT_FUNCS = 8, 5, 6


class Reader:
    def __init__(self, data: bytes, pos: int = 0, end: int | None = None) -> None:
        self.data, self.pos = data, pos
        self.end = len(data) if end is None else end

    def byte(self) -> int:
        self.pos += 1
        return self.data[self.pos - 1]

    def uleb(self) -> int:
        result = shift = 0
        while True:
            b = self.byte()
            result |= (b & 0x7F) << shift
            shift += 7
            if b < 0x80:
                return result

    def sleb(self) -> int:
        result = shift = 0
        while True:
            b = self.byte()
            result |= (b & 0x7F) << shift
            shift += 7
            if b < 0x80:
                return result - (1 << shift) if b & 0x40 else result

    def name(self) -> str:
        length = self.uleb()
        self.pos += length
        return self.data[self.pos - length : self.pos].decode(errors="replace")

    def skip_init_expr(self) -> None:
        """A constant expression: its operand may contain the `end` byte 0x0B."""
        while (op := self.byte()) != 0x0B:
            if op in (0x41, 0x42):  # i32.const, i64.const
                self.sleb()
            elif op == 0x23:  # global.get
                self.uleb()


@dataclass
class Symbol:
    kind: int
    flags: int
    name: str
    index: int = -1  # Function, global, tag or table index; for data, the segment.
    offset: int = 0  # Data: offset in its segment.
    size: int = 0

    @property
    def defined(self) -> bool:
        return not self.flags & _UNDEFINED

    @property
    def function(self) -> bool:
        return self.kind == _FUNCTION

    @property
    def root(self) -> bool:
        return self.defined and bool(self.flags & (_EXPORTED | _NO_STRIP))


@dataclass
class WasmObject:
    symbols: list[Symbol] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)
    init_functions: list[int] = field(default_factory=list)
    imported_functions: int = 0
    # Function index -> (start, end) of its body, relative to the code section payload.
    bodies: dict[int, tuple[int, int]] = field(default_factory=dict)
    # Data segment -> start of its bytes, relative to the data section payload.
    segments: list[int] = field(default_factory=list)
    segment_names: list[str] = field(default_factory=list)
    segment_lengths: list[int] = field(default_factory=list)
    # Data nodes: ranges of the data section, cut at the start of every data symbol that is
    # not an alias (`__typeid_*`), as (start, end, name, zero-initialized).
    ranges: list[tuple[int, int, str, bool]] = field(default_factory=list)
    range_starts: list[int] = field(default_factory=list)
    sections: list[tuple[int, int, int, str]] = field(default_factory=list)


def _sections(data: bytes) -> list[tuple[int, int, int, str]]:
    """(id, payload start, payload end, custom name) of every section."""
    r, out = Reader(data, 8), []
    while r.pos < len(data):
        sid, size = r.byte(), 0
        size = r.uleb()
        start, end, name = r.pos, r.pos + size, ""
        if sid == 0:
            name = Reader(data, start).name()
        out.append((sid, start, end, name))
        r.pos = end
    return out


def _count_imports(data: bytes, start: int) -> int:
    r, functions = Reader(data, start), 0
    for _ in range(r.uleb()):
        r.name()
        r.name()
        kind = r.byte()
        if kind == 0:
            r.uleb()
            functions += 1
        elif kind == 1:
            r.byte()
            r.pos = _skip_limits(r)
        elif kind == 2:
            r.pos = _skip_limits(r)
        elif kind == 3:
            r.byte()
            r.byte()
        elif kind == 4:
            r.byte()
            r.uleb()
    return functions


def _skip_limits(r: Reader) -> int:
    flags = r.byte()
    r.uleb()
    if flags & 1:
        r.uleb()
    return r.pos


def _read_bodies(obj: WasmObject, data: bytes, start: int) -> None:
    r = Reader(data, start)
    for i in range(r.uleb()):
        size = r.uleb()
        obj.bodies[obj.imported_functions + i] = (r.pos - start, r.pos - start + size)
        r.pos += size


def _read_segments(obj: WasmObject, data: bytes, start: int) -> None:
    r = Reader(data, start)
    for _ in range(r.uleb()):
        flags = r.uleb()
        if flags == 2:
            r.uleb()
        if flags != 1:
            r.skip_init_expr()
        size = r.uleb()
        obj.segments.append(r.pos - start)
        obj.segment_lengths.append(size)
        r.pos += size


def _read_symbol(r: Reader) -> Symbol:
    kind, flags = r.byte(), r.uleb()
    if kind == _DATA:
        symbol = Symbol(kind, flags, r.name())
        if not flags & _UNDEFINED:
            symbol.index, symbol.offset, symbol.size = r.uleb(), r.uleb(), r.uleb()
        return symbol
    if kind == _SECTION:
        return Symbol(kind, flags, "", r.uleb())
    index = r.uleb()
    named = not flags & _UNDEFINED or flags & _EXPLICIT_NAME
    return Symbol(kind, flags, r.name() if named else "", index)


def _read_segment_info(obj: WasmObject, sub: Reader) -> None:
    for _ in range(sub.uleb()):
        obj.segment_names.append(sub.name())
        sub.uleb()
        sub.uleb()


def _read_init_functions(obj: WasmObject, sub: Reader) -> None:
    for _ in range(sub.uleb()):
        sub.uleb()
        obj.init_functions.append(sub.uleb())


def _read_symbol_table(obj: WasmObject, sub: Reader) -> None:
    obj.symbols = [_read_symbol(sub) for _ in range(sub.uleb())]


_LINKING = {
    _SYMBOL_TABLE: _read_symbol_table,
    _SEGMENT_INFO: _read_segment_info,
    _INIT_FUNCS: _read_init_functions,
}


def _read_linking(obj: WasmObject, data: bytes, start: int, end: int) -> None:
    r = Reader(data, start)
    r.name()
    r.uleb()  # Version.
    while r.pos < end:
        kind, size = r.byte(), r.uleb()
        reader = _LINKING.get(kind)
        if reader:
            reader(obj, Reader(data, r.pos, r.pos + size))
        r.pos += size


def _function_symbols(obj: WasmObject) -> dict[int, int]:
    """Function index -> its (first) defined symbol."""
    functions: dict[int, int] = {}
    for i, s in enumerate(obj.symbols):
        if s.kind == _FUNCTION and s.defined:
            functions.setdefault(s.index, i)
    return functions


def _read_relocs(obj: WasmObject, data: bytes, start: int) -> list[tuple[int, int, int]]:
    """(target section index, offset, symbol) of every relocation."""
    r = Reader(data, start)
    r.name()
    section, out = r.uleb(), []
    for _ in range(r.uleb()):
        kind, offset, index = r.byte(), r.uleb(), r.uleb()
        if kind in _ADDEND:
            r.sleb()
        if kind != 6:  # Type indices name no symbol.
            out.append((section, offset, index))
    return out


def read(path: Path) -> WasmObject:
    data = path.read_bytes()
    obj = WasmObject(sections=_sections(data))
    for sid, start, end, name in obj.sections:
        if sid == 2:
            obj.imported_functions = _count_imports(data, start)
        elif sid == 10:
            _read_bodies(obj, data, start)
        elif sid == 11:
            _read_segments(obj, data, start)
        elif name == "linking":
            _read_linking(obj, data, start, end)
    obj_sizes(obj)
    _cut_ranges(obj)
    _link_edges(obj, data)
    return obj


def _cuts(obj: WasmObject) -> dict[int, str]:
    """Where data ranges start: every segment, and every data symbol but aliases."""
    cuts = dict(zip(obj.segments, obj.segment_names, strict=True))
    for s in obj.symbols:
        if s.kind == _DATA and s.defined and not s.name.startswith("__typeid"):
            cuts.setdefault(obj.segments[s.index] + s.offset, s.name)
    return cuts


def _cut_ranges(obj: WasmObject) -> None:
    cuts = _cuts(obj)
    starts = sorted(cuts)
    for k, start in enumerate(starts):
        segment = bisect.bisect_right(obj.segments, start) - 1
        segment_end = obj.segments[segment] + obj.segment_lengths[segment]
        end = min(segment_end, starts[k + 1]) if k + 1 < len(starts) else segment_end
        zero = obj.segment_names[segment].startswith(".bss")
        obj.ranges.append((start, end, cuts[start], zero))
    obj.range_starts = starts


def data_node(obj: WasmObject, offset: int) -> int | None:
    """The data node holding a data section offset."""
    at = bisect.bisect_right(obj.range_starts, offset) - 1
    if at < 0 or offset >= max(obj.ranges[at][1], obj.ranges[at][0] + 1):
        return None
    return len(obj.symbols) + at


def node(obj: WasmObject, symbol: int) -> int:
    """The graph node of a symbol: a function's own symbol, or the data range its address
    falls in (numbered after the symbols), since data symbols may overlap but ranges do not."""
    s = obj.symbols[symbol]
    if s.kind == _DATA and s.defined:
        found = data_node(obj, obj.segments[s.index] + s.offset)
        return found if found is not None else symbol
    return symbol


def node_size(obj: WasmObject, n: int) -> int:
    if n >= len(obj.symbols):
        start, end, _, zero = obj.ranges[n - len(obj.symbols)]
        return 0 if zero else end - start
    s = obj.symbols[n]
    return s.size if s.kind == _FUNCTION else 0


def node_name(obj: WasmObject, n: int) -> str:
    if n >= len(obj.symbols):
        return obj.ranges[n - len(obj.symbols)][2]
    return obj.symbols[n].name


class _Bodies:
    """Which function's body holds an offset of the code section."""

    def __init__(self, obj: WasmObject) -> None:
        functions = _function_symbols(obj)
        self.bodies = sorted(
            (begin, end, functions.get(i)) for i, (begin, end) in obj.bodies.items()
        )
        self.starts = [begin for begin, _, _ in self.bodies]

    def owner(self, offset: int) -> int | None:
        at = bisect.bisect_right(self.starts, offset) - 1
        return self.bodies[at][2] if at >= 0 and offset < self.bodies[at][1] else None


def _link_edges(obj: WasmObject, data: bytes) -> None:
    bodies = _Bodies(obj)
    relocations = [s for s in obj.sections if s[3] in ("reloc.CODE", "reloc.DATA")]
    for _, start, _, _ in relocations:
        for section, offset, target in _read_relocs(obj, data, start):
            in_code = obj.sections[section][0] == 10
            source = bodies.owner(offset) if in_code else data_node(obj, offset)
            if source is not None:
                obj.edges.append((source, node(obj, target)))


def obj_sizes(obj: WasmObject) -> None:
    """Each defined function symbol's size, from its body."""
    for s in obj.symbols:
        body = obj.bodies.get(s.index) if s.kind == _FUNCTION and s.defined else None
        if body:
            s.size = body[1] - body[0]
