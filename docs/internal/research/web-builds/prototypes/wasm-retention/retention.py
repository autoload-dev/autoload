"""
Why is it still in the binary? Rank what keeps code and data alive in a WebAssembly
build, from the LTO object wasm-ld writes with `-Wl,--save-temps`.

The roots are the static constructors, the entry points and every symbol the object
marks exported or no-strip. Each node's retained size is what it dominates: the bytes
that only it keeps alive, so removing it frees at least that much. `--cut REGEX` instead
removes every node whose name matches and reports what becomes unreachable, for nodes
that share what they keep.

Usage: python3 retention.py <object.lto.o> [--top N] [--cut REGEX ...] [--path NAME]
"""

import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wasm_object as wo
from dominators import ROOT, dominators, retained

_ENTRY_POINTS = ("main", "__main_argc_argv", "malloc", "free")


class Graph:
    def __init__(self, obj: wo.WasmObject) -> None:
        self.obj = obj
        self.successors: dict[int, list[int]] = defaultdict(list)
        for a, b in obj.edges:
            if a != b:
                self.successors[a].append(b)
        named = {
            i for i, s in enumerate(obj.symbols) if s.root or s.name in _ENTRY_POINTS
        }
        self.roots = sorted(wo.node(obj, i) for i in named | set(obj.init_functions))

    def size(self, n: int) -> int:
        return wo.node_size(self.obj, n)

    def name(self, n: int) -> str:
        return wo.node_name(self.obj, n)

    def reachable(self, removed: frozenset[int] = frozenset()) -> set[int]:
        seen = {r for r in self.roots if r not in removed}
        stack = list(seen)
        while stack:
            for m in self.successors[stack.pop()]:
                if m not in seen and m not in removed:
                    seen.add(m)
                    stack.append(m)
        return seen


def demangle(names: list[str]) -> list[str]:
    """C++ names demangled by `$CXXFILT` or llvm-cxxfilt, or as they are without one."""
    tool = (
        os.environ.get("CXXFILT")
        or shutil.which("llvm-cxxfilt")
        or shutil.which("c++filt")
    )
    if not tool:
        return names
    result = subprocess.run(
        [tool], input="\n".join(names), capture_output=True, text=True, check=False
    )
    lines = result.stdout.splitlines()
    return lines if len(lines) == len(names) else names


def report_top(graph: Graph, top: int) -> None:
    idom = dominators(graph.roots, graph.successors.__getitem__)
    total = retained(idom, graph.size)
    live = sum(graph.size(n) for n in idom if n != ROOT)
    print(f"{len(idom) - 1} reachable nodes, {live:,} bytes")
    ranked = sorted((n for n in total if n != ROOT), key=lambda n: -total[n])[:top]
    names = demangle([graph.name(n) for n in ranked])
    for n, name in zip(ranked, names, strict=True):
        print(f"{total[n]:>10,} {graph.size(n):>9,}  {name[:150]}")


def report_cut(graph: Graph, patterns: list[str]) -> None:
    base = graph.reachable()
    nodes = set(base)
    names = dict(
        zip(sorted(nodes), demangle([graph.name(n) for n in sorted(nodes)]), strict=True)
    )
    cut = frozenset(n for n in nodes if any(re.search(p, names[n]) for p in patterns))
    after = graph.reachable(cut)
    freed = base - after
    print(
        f"cut {len(cut)} nodes: frees {sum(graph.size(n) for n in freed):,} bytes in {len(freed)} nodes"
    )
    for n in sorted(freed, key=lambda n: -graph.size(n))[:25]:
        print(f"{graph.size(n):>10,}  {names[n][:150]}")


def _parents(graph: Graph, target: int) -> dict[int, int | None]:
    """Breadth-first parents from the roots until target is reached."""
    parent: dict[int, int | None] = dict.fromkeys(graph.roots)
    queue = deque(graph.roots)
    while queue and target not in parent:
        n = queue.popleft()
        for m in graph.successors[n]:
            parent.setdefault(m, n)
            if parent[m] == n:
                queue.append(m)
    return parent


def report_path(graph: Graph, name: str) -> None:
    """One chain of references from a root to the node named name."""
    target = next(n for n in graph.reachable() if graph.name(n) == name)
    parent = _parents(graph, target)
    chain = [target]
    while (up := parent.get(chain[-1])) is not None:
        chain.append(up)
    for line in demangle([graph.name(n) for n in reversed(chain)]):
        print(f"  {line[:160]}")


def main() -> None:
    args = sys.argv[1:]
    graph = Graph(wo.read(Path(args[0])))
    if "--cut" in args:
        report_cut(graph, args[args.index("--cut") + 1 :])
    elif "--path" in args:
        report_path(graph, args[args.index("--path") + 1])
    else:
        report_top(graph, int(args[args.index("--top") + 1]) if "--top" in args else 60)


if __name__ == "__main__":
    main()
