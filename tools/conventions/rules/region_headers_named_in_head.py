"""
region-headers-named-in-head: a region starts with a region header, which fills its line
to column 80, and the file's head names the regions in their order.
"""

import ast
import io
import re
import tokenize
from collections.abc import Generator, Iterable, Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.python_modules import parse

# The column a region header fills to with `=`.
WIDTH = 80
# The comment marker of each format with region headers, by suffix or file name.
SUFFIXES = {".py": "#", ".bzl": "#", ".gd": "#", ".cc": "//", ".h": "//", ".cpp": "//"}
NAMES = {"BUILD": "#", "BUILD.bazel": "#"}
# A region header, at any indentation and with either marker.
HEADER = re.compile(
    r"(?P<indent>\s*)(?P<marker>#|//) ==== (?P<name>[^=\s](?:[^=]*[^=\s])?) =+"
)
# A comment that looks like a section mark but is not a region header.
LOOKALIKE = re.compile(
    r"\s*(#|//)\s*(={3,}|-{3,}|\*{3,}|~{3,}|#{3,}|#?(end)?region\b|MARK:)"
)
# The list of regions in a file's head.
SECTIONS = re.compile(r"Sections:\s*(?P<names>.*?)\.(?:\s|$)")


@dataclass(frozen=True)
class Region:
    name: str
    line: int


def marker(name: str) -> str | None:
    """The comment marker of a file with region headers, or None."""
    path = PurePosixPath(name)
    if path.name in NAMES or path.name.endswith("MODULE.bazel"):
        return "#"
    return SUFFIXES.get(path.suffix)


def python_comments(text: str) -> set[int] | None:
    """The lines of a Python module that hold a comment, which strings never do."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        return {token.start[0] for token in tokens if token.type == tokenize.COMMENT}
    except tokenize.TokenError, SyntaxError:
        return None


def comment_lines(name: str, text: str) -> Iterator[tuple[int, str]]:
    """The numbered lines of a file that are comments."""
    comments = python_comments(text) if name.endswith(".py") else None
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("#", "//")) and (
            comments is None or number in comments
        ):
            yield number, line


def header(comment: str, name: str) -> str:
    """The region header of a name."""
    start = f"{comment} ==== {name} "
    return start + "=" * max(4, WIDTH - len(start))


def header_findings(
    location: Location, comment: str, found: re.Match[str]
) -> Iterator[Finding]:
    """What is wrong with a region header: its indentation, width or marker."""
    expected = header(comment, found["name"])
    if found["indent"]:
        yield Finding(location, "a region header stands at the top level")
    elif found[0] != expected:
        yield Finding(location, f"write the region header as {expected}")


def listed(head: str) -> list[str] | None:
    """The region names a file's head lists, or None without a list."""
    text = " ".join(line.strip().lstrip("#/").strip() for line in head.splitlines())
    found = SECTIONS.search(text)
    if found is None:
        return None
    return [name.strip() for name in found["names"].split(",") if name.strip()]


def python_declarations(
    module: ast.Module, regions: list[Region], lines: int
) -> Iterator[Region]:
    """The regions of a Python module that declare fewer than two names."""
    kinds = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Assign,
        ast.AnnAssign,
    )
    starts = [
        statement.lineno for statement in module.body if isinstance(statement, kinds)
    ]
    ends = [region.line for region in regions[1:]] + [lines + 1]
    for region, end in zip(regions, ends):
        if sum(region.line < start < end for start in starts) < 2:
            yield region


class RegionHeaders:
    info = RuleInfo(
        "region-headers-named-in-head",
        "Regions start with a region header the file's head names",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        for name in workspace.files:
            comment = marker(name)
            if comment is None:
                continue
            text = workspace.text(name)
            regions = yield from self.check(name, comment, text)
            if regions:
                yield from self.check_head(name, text, regions)
            if regions and name.endswith(".py"):
                lines = len(text.splitlines())
                for region in python_declarations(parse(workspace, name), regions, lines):
                    yield Finding(
                        Location(name, region.line),
                        f"region {region.name} declares fewer than two names; "
                        "merge it into its neighbour",
                    )

    @staticmethod
    def check(
        name: str, comment: str, text: str
    ) -> Generator[Finding, None, list[Region]]:
        """Report malformed region headers and section marks; return the regions."""
        regions: list[Region] = []
        for number, line in comment_lines(name, text):
            found = HEADER.fullmatch(line)
            if found is None:
                if LOOKALIKE.match(line):
                    yield Finding(
                        Location(name, number),
                        f"write a section mark as a region header: {header(comment, 'Name')}",
                    )
                continue
            yield from header_findings(Location(name, number), comment, found)
            regions.append(Region(found["name"], number))
        return regions

    @staticmethod
    def check_head(name: str, text: str, regions: list[Region]) -> Iterator[Finding]:
        """The head, everything above the first region header, names the regions."""
        head = "\n".join(text.splitlines()[: regions[0].line - 1])
        names = [region.name for region in regions]
        wanted = f"Sections: {', '.join(names)}."
        found = listed(head)
        if found is None:
            yield Finding(
                Location(name, 1), f"name the regions in the file's head: {wanted}"
            )
        elif found != names:
            yield Finding(
                Location(name, 1),
                f"the head lists {', '.join(found)}; the regions are: {wanted}",
            )
