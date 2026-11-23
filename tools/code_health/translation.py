"""How files CodeScene does not know are presented to it as Python, and its findings mapped back.

* Starlark (.bzl, optionally BUILD/MODULE files) is fed as Python; Starlark is a Python
  dialect. Documentation strings are cut to `""` first: module, function and other bare
  string statements, and every `doc = ...` string value. They are documentation, not code,
  so their length must not count towards Large Method or Lines of Code. Bazel macros
  (top-level functions whose first parameter is `name` and that declare a target with it,
  hand it to a function that does, implement a symbolic macro, or document `name:` as an
  argument) get a virtual `# @codescene(disable:"Excess Number of Function Arguments")`
  directive: a macro's parameters mirror the attributes of the rules it declares, so their
  count is no more a smell than a rule's attribute count.
* GDScript (.gd) is rewritten line by line (`func` -> `def`, `static func` -> `def`,
  `class X extends Y:` -> `class X(Y):`) and fed as Python. Its documentation is `##`
  comments, which CodeScene does not count.

Each translation records the original line of every virtual line, so findings point at the
original file.
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

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
TOP_LEVEL_DEF = re.compile(r"^def\s+(\w+)\s*\(")
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
        if line is None or self.lines is None or not 0 < line <= len(self.lines):
            return line
        return self.lines[line - 1]


def original_title(title: str, translation: Translation) -> str:
    """A finding's `function:line` title, with the line of the original file."""
    match = TITLE_LINE.match(title)
    if not match or translation.lines is None:
        return title
    return f"{match.group(1)}:{translation.original_line(int(match.group(2)))}"


# --- Bazel macros -------------------------------------------------------------------


def first_parameter(lines: list[str], index: int) -> str:
    """The first parameter of the function whose `def` is on lines[index]."""
    text, parameter = lines[index].split("(", 1)[1], ""
    for line in [text, *lines[index + 1 : index + 6]]:
        for char in line:
            if char in ",)":
                return parameter.strip()
            parameter += char
    return parameter.strip()


def target_named_after(variable: str) -> re.Pattern[str]:
    """A `name = ...` argument whose value is the variable or a string built from it."""
    v = re.escape(variable)
    return re.compile(
        rf"\bname\s*=\s*(?:{v}\b|[^,\n]*%\s*{v}\b|[^,\n]*\b{v}\s*\+|[^,\n]*\+\s*{v}\b)"
    )


TARGET_NAME = target_named_after("name")
# A local variable assigned from an expression that uses `name`, such as
# `prefix = name.replace("/", "_")`.
DERIVED_NAME = re.compile(r"^\s+(\w+)\s*=\s*[^=\n]*\bname\b", re.MULTILINE)
CALL = re.compile(r"\b(\w+)\s*\(")
SYMBOLIC_MACRO = re.compile(r"=\s*macro\(")
IMPLEMENTATION = re.compile(r"\bimplementation\s*=\s*(\w+)")
NAME_ARG_DOC = re.compile(r"^\s+name:\s", re.MULTILINE)
RETURNS_VALUE = re.compile(r"^\s+return\s+\S", re.MULTILINE)
# CodeScene's default function_max_arguments for Python; only macros above it
# need the exemption, so only they are counted and annotated.
MAX_ARGUMENTS = 4


def parameter_count(lines: list[str], index: int) -> int:
    """The number of parameters of the function whose `def` is on lines[index]."""
    signature, depth = "", 1
    for char in "".join(lines[index : index + 60]).split("(", 1)[1]:
        depth += char in "([{"
        depth -= char in ")]}"
        if depth == 0:
            break
        signature += char if depth == 1 or char not in "," else ";"
    signature = re.sub(r"#[^\n]*", "", signature)
    return sum(1 for part in signature.split(",") if part.strip())


def top_level_functions(lines: list[str]) -> dict[str, tuple[int, str]]:
    """Each top-level function: (index of its def line, its source text)."""
    functions: dict[str, tuple[int, str]] = {}
    current, start = None, 0
    for index, line in enumerate([*lines, "<end>"]):
        is_top = (
            line.strip() and not line[0].isspace() and not line.startswith(("#", ")"))
        )
        if is_top and current:
            functions[current] = (start, "".join(lines[start:index]))
            current = None
        match = TOP_LEVEL_DEF.match(line)
        if match:
            current, start = match.group(1), index
    return functions


def symbolic_macro_implementations(lines: list[str]) -> set[str]:
    names, inside = set(), False
    for line in lines:
        inside = inside or bool(SYMBOLIC_MACRO.search(line))
        match = IMPLEMENTATION.search(line) if inside else None
        if match:
            names.add(match.group(1))
        inside = inside and not match and not line.startswith(")")
    return names


Functions = dict[str, tuple[int, str]]  # name -> (index of the def line, source text)


def calls_any(body: str, name: str, known: set[str]) -> bool:
    """Whether a function body calls one of the known functions other than itself."""
    return bool(known & (set(CALL.findall(body)) - {name}))


def table_driven_macros(candidates: Functions) -> set[str]:
    """Table-driven macros declare their targets indirectly; they document `name`
    like a target and return nothing, unlike helpers that compute declarations."""
    return {
        name
        for name, (_, body) in candidates.items()
        if NAME_ARG_DOC.search(body) and not RETURNS_VALUE.search(body)
    }


def name_passing_macros(
    candidates: Functions, declarers: set[str], macros: set[str]
) -> set[str]:
    """A function that hands its name to a declaring function is a macro too."""
    macros = set(macros)
    while True:
        found = {
            name
            for name, (_, body) in candidates.items()
            if name not in macros and calls_any(body, name, declarers | macros)
        }
        if not found:
            return macros
        macros |= found


def declares_target(body: str) -> bool:
    """Whether a function body declares a target named after `name`, directly or through
    a local variable derived from it."""
    derived = set(DERIVED_NAME.findall(body)) - {"name"}
    return any(
        pattern.search(body)
        for pattern in [TARGET_NAME, *map(target_named_after, sorted(derived))]
    )


def macros_of(lines: list[str]) -> dict[str, int]:
    """Bazel macros: functions whose first parameter is `name` and that declare
    a target with it (`name = name...`), pass it on to another macro, or implement
    a symbolic macro. Returns each macro's def line index."""
    functions = top_level_functions(lines)
    candidates = {
        name: function
        for name, function in functions.items()
        if re.match(r"name\b", first_parameter(lines, function[0]))
    }
    # Functions of any signature that declare targets, e.g. _executable(rule_, name, ...).
    declarers = {name for name, (_, body) in functions.items() if declares_target(body)}
    declarers |= symbolic_macro_implementations(lines)
    macros = (declarers & set(candidates)) | table_driven_macros(candidates)
    macros = name_passing_macros(candidates, declarers, macros)
    return {name: candidates[name][0] for name in macros}


# --- documentation strings --------------------------------------------------------

Position = tuple[int, int]  # tokenize's (1-based row, column)
Span = tuple[Position, Position]

STATEMENT_START = {tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}
VALUE_END = {",", ")"}


def _significant(tokens: list[tokenize.TokenInfo]) -> list[tokenize.TokenInfo]:
    """The tokens without line continuations and comments."""
    return [t for t in tokens if t.type not in (tokenize.NL, tokenize.COMMENT)]


def _is_op(token: tokenize.TokenInfo, text: str) -> bool:
    return token.type == tokenize.OP and token.string == text


def _string_run_end(tokens: list[tokenize.TokenInfo], index: int) -> int:
    """The index of the last string of the strings that start at index, which follow each
    other directly or joined by `+`."""
    end = index
    while end + 1 < len(tokens):
        following = tokens[end + 1]
        if following.type == tokenize.STRING:
            end += 1
        elif (
            _is_op(following, "+")
            and end + 2 < len(tokens)
            and tokens[end + 2].type == tokenize.STRING
        ):
            end += 2
        else:
            break
    return end


def _bare_string(tokens: list[tokenize.TokenInfo], index: int) -> Span | None:
    """The span of a statement that is only strings, such as a docstring, starting at index."""
    starts_statement = index == 0 or tokens[index - 1].type in STATEMENT_START
    if not starts_statement or tokens[index].type != tokenize.STRING:
        return None
    end = _string_run_end(tokens, index)
    after = tokens[end + 1] if end + 1 < len(tokens) else None
    if after is not None and after.type not in (tokenize.NEWLINE, tokenize.ENDMARKER):
        return None
    return tokens[index].start, tokens[end].end


def _doc_value(tokens: list[tokenize.TokenInfo], index: int) -> Span | None:
    """The span of the string value of `doc = ...` whose `doc` is at index."""
    if tokens[index].string != "doc" or index + 2 >= len(tokens):
        return None
    if not _is_op(tokens[index + 1], "="):
        return None
    first = index + 2
    parenthesized = _is_op(tokens[first], "(")
    start = first + parenthesized
    if start >= len(tokens) or tokens[start].type != tokenize.STRING:
        return None
    end = _string_run_end(tokens, start)
    if parenthesized:
        if end + 1 >= len(tokens) or not _is_op(tokens[end + 1], ")"):
            return None
        end += 1
    after = tokens[end + 1] if end + 1 < len(tokens) else None
    if after is None:
        return None
    if after.type != tokenize.NEWLINE and not (
        after.type == tokenize.OP and after.string in VALUE_END
    ):
        return None
    return tokens[first].start, tokens[end].end


def documentation_spans(source: str) -> list[Span]:
    """The spans of a Starlark source's documentation strings, in order."""
    tokens = _significant(list(tokenize.generate_tokens(io.StringIO(source).readline)))
    spans: list[Span] = []
    for index, token in enumerate(tokens):
        if spans and token.start < spans[-1][1]:
            continue
        span = (
            _doc_value(tokens, index)
            if token.type == tokenize.NAME
            else _bare_string(tokens, index)
        )
        if span:
            spans.append(span)
    return spans


def cut_spans(lines: list[str], spans: list[Span]) -> tuple[list[str], list[int]]:
    """The lines with each span replaced by `""`, and the original row of each line."""
    out: list[str] = []
    origin: list[int] = []
    text, start, row, column = "", 1, 1, 0

    def finish_line() -> None:
        nonlocal text, start, row, column
        out.append(text + lines[row - 1][column:])
        origin.append(start)
        text, row, column = "", row + 1, 0
        start = row

    for (first_row, first_column), (last_row, last_column) in spans:
        while row < first_row:
            finish_line()
        text += lines[row - 1][column:first_column] + '""'
        row, column = last_row, last_column
    while row <= len(lines):
        finish_line()
    return out, origin


def without_documentation(path: str, lines: list[str]) -> tuple[list[str], list[int]]:
    """The Starlark lines with their documentation strings cut, and each line's origin."""
    try:
        spans = documentation_spans("".join(lines))
    except (tokenize.TokenError, SyntaxError) as error:
        print(f"warning: {path}: documentation kept: {error}", file=sys.stderr)
        spans = []
    return cut_spans(lines, spans)


# --- translations -------------------------------------------------------------------


def starlark(path: str, source: str, macro_arguments: bool) -> Translation:
    """Starlark as Python, without its documentation; macros exempt from the
    argument-count rule unless macro_arguments counts them."""
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
