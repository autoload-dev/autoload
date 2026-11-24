"""
Dominator trees of reference graphs, by Cooper, Harvey and Kennedy's iterative algorithm
("A Simple, Fast Dominance Algorithm"), and the size each node retains.

A virtual root, ROOT, precedes all real roots, so a graph with many roots has one tree.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable

ROOT = -1
Successors = Callable[[int], Iterable[int]]


def postorder(roots: list[int], successors: Successors) -> list[int]:
    """The nodes reachable from ROOT, which leads to every root, in DFS postorder."""
    order, seen = [], {ROOT}
    stack = [(ROOT, iter(roots))]
    while stack:
        n, children = stack[-1]
        nxt = next((m for m in children if m not in seen), None)
        if nxt is None:
            order.append(n)
            stack.pop()
            continue
        seen.add(nxt)
        stack.append((nxt, iter(successors(nxt))))
    return order


def _predecessors(
    roots: list[int], order: list[int], successors: Successors
) -> dict[int, list[int]]:
    predecessors: dict[int, list[int]] = defaultdict(list)
    for r in roots:
        predecessors[r].append(ROOT)
    for a in order:
        if a != ROOT:
            for b in successors(a):
                predecessors[b].append(a)
    return predecessors


class _Tree:
    def __init__(self, order: list[int]) -> None:
        self.number = {n: i for i, n in enumerate(order)}
        self.idom = {ROOT: ROOT}

    def intersect(self, a: int, b: int) -> int:
        while a != b:
            while self.number[a] < self.number[b]:
                a = self.idom[a]
            while self.number[b] < self.number[a]:
                b = self.idom[b]
        return a

    def update(self, n: int, predecessors: list[int]) -> bool:
        """Set n's dominator from its processed predecessors; whether it changed."""
        done = [p for p in predecessors if p in self.idom]
        new = done[0]
        for p in done[1:]:
            new = self.intersect(p, new)
        changed = self.idom.get(n) != new
        self.idom[n] = new
        return changed


def dominators(roots: list[int], successors: Successors) -> dict[int, int]:
    """Each reachable node's immediate dominator; ROOT dominates the roots."""
    order = postorder(roots, successors)
    predecessors = _predecessors(roots, order, successors)
    tree = _Tree(order)
    changed = True
    while changed:
        changed = False
        for n in reversed(order[:-1]):
            changed |= tree.update(n, predecessors[n])
    return tree.idom


def retained(idom: dict[int, int], size: Callable[[int], int]) -> dict[int, int]:
    """Each node's own size plus everything it dominates."""
    children: dict[int, list[int]] = defaultdict(list)
    for n, d in idom.items():
        if n != ROOT:
            children[d].append(n)
    total: dict[int, int] = {}
    stack = [(ROOT, False)]
    while stack:
        n, done = stack.pop()
        if not done:
            stack.append((n, True))
            stack.extend((c, False) for c in children[n])
            continue
        own = size(n) if n != ROOT else 0
        total[n] = own + sum(total[c] for c in children[n])
    return total
