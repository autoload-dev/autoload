"""
Check an Android application's Maven modules against Godot's Maven graph.

Godot's Maven graph is what Gradle resolves for the Maven dependencies Godot
declares for its template activity and Android shell library; each version in
it is a minimum. The application's modules are the `group:artifact:version`
coordinates of its Java closure, one per line. A module present in both and
resolved below its minimum by Maven's version order is a shortfall; a module
present in only one of them is ignored.

Without a shortfall the template activity source is copied unchanged to the
output, which the application compiles. With one, the diagnostic names each
shortfall and the check fails, so javac never compiles the activity against
classes the resolved modules lack.
"""

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Maven's qualifier order (ComparableVersion); the empty qualifier is a release.
_QUALIFIERS = ["alpha", "beta", "milestone", "rc", "snapshot", "", "sp"]
_ALIASES = {"ga": "", "final": "", "release": "", "cr": "rc"}
_SHORT = {"a": "alpha", "b": "beta", "m": "milestone"}


def _qualifier(value: str) -> str:
    """The string Maven compares a qualifier by: known ones by rank, others after."""
    if value in _QUALIFIERS:
        return str(_QUALIFIERS.index(value))
    return f"{len(_QUALIFIERS)}-{value}"


def _order[T: (int, str)](left: T, right: T) -> int:
    return (left > right) - (left < right)


_RELEASE = _qualifier("")


@dataclass
class _Number:
    """A numeric item of a parsed version."""

    value: int

    def is_null(self) -> bool:
        return self.value == 0

    def compare(self, other: _Item | None) -> int:
        if other is None:
            return 0 if self.value == 0 else 1
        if isinstance(other, _Number):
            return _order(self.value, other.value)
        return 1


@dataclass
class _Qualifier:
    """A qualifier item of a parsed version, such as rc or a vendor suffix."""

    value: str

    def is_null(self) -> bool:
        return self.value == ""

    def compare(self, other: _Item | None) -> int:
        mine = _qualifier(self.value)
        if other is None:
            return _order(mine, _RELEASE)
        if isinstance(other, _Qualifier):
            return _order(mine, _qualifier(other.value))
        return -1


@dataclass
class _Sublist:
    """The items after a '-' or a change between digits and letters."""

    items: list[_Item] = field(default_factory=list)

    def is_null(self) -> bool:
        return not self.items

    def compare(self, other: _Item | None) -> int:
        if other is None:
            return self.items[0].compare(None) if self.items else 0
        if isinstance(other, _Number):
            return -1
        if isinstance(other, _Qualifier):
            return 1
        for index in range(max(len(self.items), len(other.items))):
            left = self.items[index] if index < len(self.items) else None
            right = other.items[index] if index < len(other.items) else None
            if left is None:
                assert right is not None
                result = -right.compare(None)
            else:
                result = left.compare(right)
            if result:
                return result
        return 0


_Item = _Number | _Qualifier | _Sublist


def _token(digits: bool, text: str, followed_by_digit: bool = False) -> _Item:
    if digits:
        return _Number(int(text))
    if followed_by_digit:
        text = _SHORT.get(text, text)
    return _Qualifier(_ALIASES.get(text, text))


def _normalize(sublist: _Sublist) -> None:
    """Drop trailing null items, looking past non-null sublists as Maven does."""
    items = sublist.items
    for index in range(len(items) - 1, -1, -1):
        if items[index].is_null():
            del items[index]
        elif not isinstance(items[index], _Sublist):
            break


def parse_version(version: str) -> _Sublist:
    """Parse a version as Maven's ComparableVersion does."""
    text = version.lower()
    root = _Sublist()
    current = root
    stack = [root]
    digits = False
    start = 0

    def descend() -> _Sublist:
        sublist = _Sublist()
        current.items.append(sublist)
        stack.append(sublist)
        return sublist

    for index, char in enumerate(text):
        if char in ".-":
            current.items.append(
                _Number(0) if index == start else _token(digits, text[start:index])
            )
            start = index + 1
            if char == "-":
                current = descend()
        elif char.isdigit():
            if not digits and index > start:
                current.items.append(_token(False, text[start:index], True))
                start = index
                current = descend()
            digits = True
        else:
            if digits and index > start:
                current.items.append(_token(True, text[start:index]))
                start = index
                current = descend()
            digits = False
    if len(text) > start:
        current.items.append(_token(digits, text[start:]))
    while stack:
        _normalize(stack.pop())
    return root


def compare_versions(left: str, right: str) -> int:
    """Order two Maven versions: negative, zero or positive."""
    return parse_version(left).compare(parse_version(right))


def read_graph(path: Path) -> dict[str, str]:
    """The minimum version of each `group:artifact` in a rules_jvm_external lock."""
    artifacts = json.loads(path.read_text())["artifacts"]
    graph: dict[str, str] = {}
    for key, entry in artifacts.items():
        group, artifact = key.split(":")[:2]
        graph[f"{group}:{artifact}"] = entry["version"]
    return graph


def read_coordinates(path: Path) -> dict[str, str]:
    """
    The resolved version of each `group:artifact` of the application.

    A module listed at several versions, such as from a second Maven installation,
    counts at its lowest.
    """
    resolved: dict[str, str] = {}
    for line in path.read_text().splitlines():
        group, artifact, version = line.split(":")
        module = f"{group}:{artifact}"
        if module not in resolved or compare_versions(version, resolved[module]) < 0:
            resolved[module] = version
    return resolved


def shortfalls(
    resolved: dict[str, str], minimums: dict[str, str]
) -> list[tuple[str, str, str]]:
    """Modules of both resolved below their minimum, sorted by `group:artifact`."""
    return [
        (module, resolved[module], minimums[module])
        for module in sorted(resolved.keys() & minimums.keys())
        if compare_versions(resolved[module], minimums[module]) < 0
    ]


def diagnostic(
    application: str, engine_minor: str, found: list[tuple[str, str, str]]
) -> str:
    width = max(len(module) for module, _, _ in found)
    lines = [
        (
            f"{application}: the shared Maven installation resolves modules below "
            f"Godot {engine_minor}'s minimums."
        ),
        (
            "Godot's template activity and Android shell library need, as Godot's "
            "Gradle export resolves them:"
        ),
    ]
    lines += [
        f"  {module.ljust(width)}  resolved {version}  minimum {minimum}"
        for module, version, minimum in found
    ]
    lines += [
        (
            "Fix: remove the forced version or override that lowers these modules; "
            "a maven installation"
        ),
        (
            'with another resolver switches to resolver = "gradle". Then repin with '
            "`REPIN=1 bazel run @maven//:pin`."
        ),
        "See docs/public/platforms.md#android.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coordinates", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--application", required=True)
    parser.add_argument("--engine-minor", required=True)
    args = parser.parse_args()
    found = shortfalls(read_coordinates(args.coordinates), read_graph(args.graph))
    if found:
        print(diagnostic(args.application, args.engine_minor, found), file=sys.stderr)
        return 1
    shutil.copyfile(args.source, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
