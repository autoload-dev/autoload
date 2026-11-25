"""How files CodeScene does not know are presented to it as Python, and its findings mapped back.

* Starlark (.bzl, optionally BUILD/MODULE files) is fed as Python; Starlark is a Python
  dialect. Its documentation strings are cut to `""` first (documentation.py), and its
  Bazel macros (macros.py) get a virtual
  `# @codescene(disable:"Excess Number of Function Arguments")` directive.
* GDScript (.gd) is rewritten line by line (`func` -> `def`, `static func` -> `def`,
  `class X extends Y:` -> `class X(Y):`) and fed as Python. Its documentation is `##`
  comments, which CodeScene does not count.

Each translation records the original line of every virtual line, so findings point at the
original file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.code_health.documentation import without_documentation
from tools.code_health.macros import MAX_ARGUMENTS, macros_of, parameter_count

# File types the CodeScene CLI analyses natively (from its own error message).
NATIVE = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".ipp",
    ".cs",
    ".java",
    ".groovy",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".mts",
    ".cts",
    ".jsx",
    ".tsx",
    ".vue",
    ".m",
    ".mm",
    ".scala",
    ".py",
    ".pyi",
    ".swift",
    ".go",
    ".dart",
    ".vb",
    ".php",
    ".rs",
    ".rb",
    ".kt",
    ".kts",
    ".pl",
    ".pm",
    ".erl",
    ".hrl",
    ".ex",
    ".exs",
    ".clj",
    ".cljc",
    ".cljs",
    ".ps1",
    ".psm1",
    ".psd1",
    ".tcl",
    ".cls",
    ".trigger",
}

GD_FUNC = re.compile(r"^(\s*)(?:static\s+)?func\s")
GD_CLASS = re.compile(r"^(\s*)class\s+(\w+)\s+extends\s+([\w.]+)\s*:")
MACRO_DIRECTIVE = '# @codescene(disable:"Excess Number of Function Arguments")\n'
TITLE_LINE = re.compile(r"^(.*):(\d+)$")


@dataclass
class Translation:
    virtual_name: str
    source: str
    # The original 1-based line of each virtual line; None when the lines are the same.
    lines: list[int] | None = None
    macros: list[str] = field(default_factory=list)

    def original_line(self, line: int | None) -> int | None:
        if line is None or self.lines is None:
            return line
        return self.lines[line - 1] if 0 < line <= len(self.lines) else line


def original_title(title: str, translation: Translation) -> str:
    """A finding's `function:line` title, with the line of the original file."""
    match = TITLE_LINE.match(title)
    if not match or translation.lines is None:
        return title
    return f"{match.group(1)}:{translation.original_line(int(match.group(2)))}"


def starlark(path: str, source: str, macro_arguments: bool) -> Translation:
    """
    Starlark as Python, without its documentation; macros exempt from the
    argument-count rule unless macro_arguments counts them.
    """
    lines = source.splitlines(keepends=True)
    # Macros are found in the original lines: a table-driven macro documents `name:`.
    exempt = (
        {}
        if macro_arguments
        else {
            index + 1: name
            for name, index in macros_of(lines).items()
            if parameter_count(lines, index) > MAX_ARGUMENTS
        }
    )
    kept, origin = without_documentation(path, lines)
    out: list[str] = []
    rows: list[int] = []
    macros: list[str] = []
    for line, row in zip(kept, origin, strict=True):
        macro = exempt.pop(row, None)
        if macro:
            out.append(MACRO_DIRECTIVE)
            rows.append(row)
            macros.append(macro)
        out.append(line)
        rows.append(row)
    return Translation(path + ".py", "".join(out), rows, macros)


def gdscript(path: str, source: str) -> Translation:
    """GDScript rewritten line by line into Python CodeScene can parse."""
    lines = []
    for line in source.splitlines(keepends=True):
        line = GD_FUNC.sub(r"\1def ", line)
        line = GD_CLASS.sub(r"\1class \2(\3):", line)
        lines.append(line)
    return Translation(path + ".py", "".join(lines))


def translate(path: str, source: str, macro_arguments: bool) -> Translation:
    """The virtual file name and the source CodeScene should analyse."""
    suffix = Path(path).suffix
    if suffix in NATIVE:
        return Translation(path, source)
    if suffix == ".gd":
        return gdscript(path, source)
    return starlark(path, source, macro_arguments)
