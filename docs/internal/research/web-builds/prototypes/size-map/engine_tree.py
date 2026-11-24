"""
The engine's size tree for the size map: every function and data range reachable in the
LTO object (`retention.py`'s graph), by area and by dominator.

An area comes from the symbol's class or function name (`AREAS`, first match). A symbol
whose name says nothing, such as a table without a class, belongs to its immediate
dominator's area: the code that alone keeps it. Sizes are bytes before wasm-opt.

Usage: python3 engine_tree.py <object.lto.o> <gen_cpp output .inc> <engine.json>
       (set CXXFILT to llvm-cxxfilt for demangled names)
"""

import importlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "wasm-retention"))
sys.setrecursionlimit(100_000)
retention = importlib.import_module("retention")
wasm_object = importlib.import_module("wasm_object")
dominators = importlib.import_module("dominators")
ROOT = dominators.ROOT

AREAS = [
    ("Spielcode (GDScript → C++)", r"^gd_|GDScriptNative"),
    ("GDScript-Laufzeit", r"GDScript"),
    (
        "Text & Schriften",
        r"TextServer|^FT_|^ft_|^tt_|^TT_|sfnt|^af_|autofit|^ps_|^cff|Font|Glyph|^FTC_|^t1_|^pfr|^bdf|^pcf|^psh|^T1_",
    ),
    (
        "Rendering (GLES3, Shader)",
        r"GLES3|Rasterizer|Shader|Render|Material|Mesh|Texture|Environment|Sky|Camera|Light|Fog|Particles|Decal|Lightmap|Reflection|Occluder|VoxelGI|MultiMesh|Canvas|LTC|glad|^gl[A-Z_]|^emscripten_gl",
    ),
    (
        "Szene & UI",
        r"^Node|Control|Theme|default_theme|Label|Button|Container|SceneTree|Tween|Window|Viewport|CanvasItem|Node3D|Animation|Popup|Range|Panel|Style|Scroll|Tree|Scene|Visual|Instance|Timer|Marker|Sprite|Box|Margin|Color|Rich|Path|Input|Gui|Layout|World",
    ),
    (
        "Ressourcen & Dateien",
        r"Resource|FileAccess|DirAccess|Image|^png|PNG|[Ww]eb[Pp]|^Decode|^VP8|ZSTD|zstd|^HUF|^FSE|Compression|VariantParser|VariantWriter|PackedData|PCK|ConfigFile|decode_variant|encode_variant|inflate|deflate|crc|zlib|fastlz|JSON|Marshall|Translation|^z_|^_tr_|Crypto|HashingContext|MD5|SHA|sha|md5|mbedtls",
    ),
    ("Audio", r"Audio"),
    (
        "Web-Plattform",
        r"OS_Web|DisplayServerWeb|godot_js|emscripten|Web|OS_Unix|JavaScript",
    ),
    (
        "Start & Registrierung",
        r"^Main$|^Main::|register_|initialize_|unregister|godot_web_main|^ClassDB::creator|_bind_methods|initialize_class",
    ),
    (
        "Variant & Kern",
        r"Variant|String|Array|Dictionary|Vector|HashMap|HashSet|CowData|Object|ClassDB|MethodBind|Callable|Signal|Math|Projection|Transform|Basis|Quaternion|AABB|Rect2|Plane|NodePath|ProjectSettings|Engine|Memory|PropertyInfo|Packed|List|RBMap|RBSet|LocalVector|Thread|Mutex|Semaphore|^OS|Time|Random|Expression|Error|_err_print|print_|Logger|CoreBind|MessageQueue|Char|Unicode|xid_|caps_table|lowercase|uppercase|vformat|itos|rtos|WorkerThreadPool|ObjectDB|Script|Ref",
    ),
    (
        "C/C++-Laufzeit",
        r"^__|^std::|malloc|^free$|^calloc$|^realloc$|^mem|^str[a-z]*$|printf|dlmalloc|operator new|operator delete|^abort$|^qsort|^sbrk|^atexit|^pthread|^_Unwind|^setjmp|^longjmp|^(exp|log|pow|sin|cos|tan|sqrt|scalbn|frexp|fmod|floor|ceil|round|atan2?|acos|asin|ldexp|modf|cbrt|hypot)f?$|^__cxa|^fwrite|^fputs|^fflush|^isw?[a-z]+$|^to[a-z]+$|^wcs|^mbs|^atoi|^strto",
    ),
]
_PATTERNS = [(area, re.compile(pattern)) for area, pattern in AREAS]
# Libraries whose functions share a prefix: one group each, whatever their area.
_LIBRARIES = [
    (r"^(FT_|ft_|tt_|TT_|af_|ps_|cff|t1_|pfr|sfnt|psh|FTC_)", "FreeType"),
    (r"^(png|PNG)", "libpng"),
    (r"^(ZSTD|HUF|FSE|zstd)", "zstd"),
    (r"^(VP8|WebP|Decode)", "libwebp"),
    (r"^(inflate|deflate|z_|_tr_|crc|adler)", "zlib"),
]
# The display areas: twelve name areas fold into eight colors.
MERGE = {
    "Spielcode (GDScript → C++)": "GDScript",
    "GDScript-Laufzeit": "GDScript",
    "Audio": "Sonstiges",
    "Web-Plattform": "Sonstiges",
    "C/C++-Laufzeit": "Sonstiges",
    "Geteilt (von mehreren gehalten)": "Sonstiges",
}
SMALL_SYMBOL, SMALL_GROUP, SMALL_DOMINATED = 1500, 2500, 3000


def clean(name: str) -> str:
    """A data range's symbol without its section prefix, for demangling."""
    name = re.sub(r"^\.(rodata|data|bss|tdata)\.", "", name)
    return re.sub(r"\.\d+$", "", re.sub(r"^\.L", "", name))


def owner(name: str) -> str:
    """The class (or free function) a demangled name belongs to."""
    for prefix in (
        "vtable for ",
        "typeinfo for ",
        "typeinfo name for ",
        "guard variable for ",
    ):
        name = name.removeprefix(prefix)
    depth, kept = 0, []
    for ch in name:  # Template arguments go.
        depth += {"<": 1, ">": -1}.get(ch, 0)
        depth = max(depth, 0)
        if depth == 0 and ch not in "<>":
            kept.append(ch)
    flat = "".join(kept).split("(")[0]
    flat = re.sub(r"^[\w:\s\*&]*\s(?=[\w:]+$)", "", flat).strip()  # The return type goes.
    parts = [p for p in flat.split("::") if p]
    return "::".join(parts[:-1]) if len(parts) >= 2 else (parts[0] if parts else name)


def scripts(inc: Path) -> list[tuple[str, str]]:
    """(symbol prefix, script path) of every compiled class, longest prefix first."""
    by_script: dict[str, set[str]] = defaultdict(set)
    rows = re.findall(r'\{ "([^"]+)", "[^"]+", &(gd_\w+?)_entry \}', inc.read_text())
    for fqcn, symbol in rows:
        by_script[fqcn].add(symbol)
    prefixes = []
    for fqcn, symbols in by_script.items():
        common = min(symbols, key=len)
        while not all(s.startswith(common) for s in symbols):
            common = common[:-1]
        prefixes.append((common.rstrip("_"), fqcn.removeprefix("res://")))
    return sorted(prefixes, key=lambda p: -len(p[0]))


class Areas:
    """Each reachable node's area and group."""

    def __init__(
        self,
        graph: Any,
        names: dict[int, str],
        idom: dict[int, int],
        prefixes: list[tuple[str, str]],
    ) -> None:
        self.graph, self.names, self.idom, self.prefixes = graph, names, idom, prefixes
        self.memo: dict[int, tuple[str, str]] = {}

    def is_data(self, n: int) -> bool:
        return n >= len(self.graph.obj.symbols)

    def direct(self, n: int) -> tuple[str, str] | None:
        """The area its own name gives, or None."""
        name = self.names[n]
        if name.startswith("gd_"):
            return AREAS[0][0], self.script(name)
        o = owner(name)
        if self.is_data(n) and o == name:
            return None
        area = _area_of(o) or (_area_of(name) if o == name else None)
        return None if area is None else (area, self.group(n, area, o))

    def script(self, name: str) -> str:
        return next((s for p, s in self.prefixes if name.startswith(p)), "Spielcode")

    def group(self, n: int, area: str, o: str) -> str:
        library = next((g for p, g in _LIBRARIES if re.match(p, o)), None)
        if library:
            return library
        if area == "C/C++-Laufzeit":
            return "Daten ohne Namen" if self.is_data(n) else "libc / libc++"
        return o

    def raw(self, n: int) -> tuple[str, str]:
        if n not in self.memo:
            found = self.direct(n)
            if found is None:
                d = self.idom.get(n, ROOT)
                kind = "Daten" if self.is_data(n) else "Code"
                found = (
                    self.raw(d)
                    if d != ROOT
                    else ("Geteilt (von mehreren gehalten)", kind)
                )
            self.memo[n] = found
        return self.memo[n]

    def of(self, n: int) -> tuple[str, str]:
        """The display area and group."""
        area, group = self.raw(n)
        merged = MERGE.get(area, area)
        if merged == "Sonstiges":
            group = f"{area.split(' (')[0]}: {group}"
        return merged, group


def node(
    name: str, size: int, kids: list[dict] | None = None, area: str | None = None
) -> dict:
    d: dict = {"n": name[:160]}
    if kids:
        d["c"] = kids
    else:
        d["v"] = size
    if area:
        d["a"] = area
    return d


def _area_of(name: str) -> str | None:
    return next((a for a, p in _PATTERNS if p.search(name)), None)


def _with_rest(nodes: list[dict], rest: int, size: int, label: str) -> list[dict]:
    """nodes, and one node for the rest when there is one."""
    return nodes + ([node(f"{rest} {label}", size)] if size else [])


class _ByArea:
    """Area, then group, then symbol."""

    def __init__(self, graph: Any, names: dict[int, str]) -> None:
        self.graph, self.names = graph, names

    def total(self, ns: list[int]) -> int:
        return sum(self.graph.size(x) for x in ns)

    def leaves(self, ns: list[int]) -> list[dict]:
        ns = sorted(ns, key=lambda n: -self.graph.size(n))
        big = [x for x in ns if self.graph.size(x) >= SMALL_SYMBOL][:40]
        rest = ns[len(big) :]
        nodes = [node(self.names[x], self.graph.size(x)) for x in big]
        return _with_rest(nodes, len(rest), self.total(rest), "kleinere")

    def area(self, area: str, groups: dict[str, list[int]]) -> dict:
        ranked = sorted(groups.items(), key=lambda kv: -self.total(kv[1]))
        big = [(k, v) for k, v in ranked if self.total(v) >= SMALL_GROUP][:60]
        rest = [x for _, v in ranked[len(big) :] for x in v]
        nodes = [node(k, 0, self.leaves(v)) for k, v in big]
        parts = _with_rest(
            nodes, len(ranked) - len(big), self.total(rest), "kleinere Gruppen"
        )
        return node(area, 0, parts, area)


def by_area(graph: Any, names: dict[int, str], areas: Areas, reach: list[int]) -> dict:
    tree: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for n in (n for n in reach if graph.size(n)):
        area, group = areas.of(n)
        tree[area][group].append(n)
    build = _ByArea(graph, names)
    return node("Alles", 0, [build.area(a, groups) for a, groups in tree.items()])


class _ByDominator:
    """Each node holds what it alone keeps alive."""

    def __init__(
        self, graph: Any, names: dict[int, str], areas: Areas, idom: dict[int, int]
    ) -> None:
        self.graph, self.names, self.areas = graph, names, areas
        self.retained = dominators.retained(idom, graph.size)
        self.children: dict[int, list[int]] = defaultdict(list)
        for n, d in idom.items():
            if n != ROOT:
                self.children[d].append(n)

    def visit(self, n: int, depth: int) -> dict:
        kids = sorted(self.children[n], key=lambda c: -self.retained[c])
        big = (
            [c for c in kids if self.retained[c] >= SMALL_DOMINATED] if depth < 14 else []
        )
        name = self.names.get(n, "Alles")
        result = (
            node(name, 0, self.inner(n, kids, big, depth))
            if big
            else node(name, self.retained[n])
        )
        if n != ROOT:
            result["a"] = self.areas.of(n)[0]
        return result

    def inner(self, n: int, kids: list[int], big: list[int], depth: int) -> list[dict]:
        nodes = [self.visit(c, depth + 1) for c in big]
        own = self.graph.size(n) if n != ROOT else 0
        nodes += [node("(eigener Code/Daten)", own)] if own else []
        rest = sum(self.retained[c] for c in kids[len(big) :])
        return _with_rest(nodes, len(kids) - len(big), rest, "kleinere")


def by_dominator(
    graph: Any, names: dict[int, str], areas: Areas, idom: dict[int, int]
) -> dict:
    return _ByDominator(graph, names, areas, idom).visit(ROOT, 0)


def main() -> None:
    obj, inc, out = map(Path, sys.argv[1:4])
    graph = retention.Graph(wasm_object.read(obj))
    reach = sorted(graph.reachable())
    raw_names = [clean(graph.name(n)) for n in reach]
    names = dict(zip(reach, retention.demangle(raw_names), strict=True))
    idom = dominators.dominators(graph.roots, graph.successors.__getitem__)
    areas = Areas(graph, names, idom, scripts(inc))
    data = {
        "total": sum(graph.size(n) for n in reach),
        "areas": by_area(graph, names, areas, reach),
        "dominators": by_dominator(graph, names, areas, idom),
    }
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"{data['total']:,} bytes before wasm-opt")


if __name__ == "__main__":
    main()
