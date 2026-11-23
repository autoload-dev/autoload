"""Cutting the documentation strings out of Starlark before CodeScene scores it.

Documentation is not code, so its length must not count towards Large Method or Lines of
Code. Two kinds of expressions are documentation when they are made only of string
literals: statements, such as module and function docstrings, and the values of `doc = ...`
arguments. Starlark parses as Python, so `ast` finds them whatever their layout. Each is
replaced by `""`, which keeps the source valid, and the lines it spanned collapse into one.
"""

from __future__ import annotations

import ast
import sys

Position = tuple[int, int]  # (1-based row, character column)
Span = tuple[Position, Position]


def _is_text(node: ast.expr) -> bool:
    """Whether an expression is only string literals, joined side by side or by `+`."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return all(map(_is_text, (node.left, node.right)))
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _documentation(node: ast.AST) -> ast.expr | None:
    """The documentation a statement or keyword argument is, or None."""
    match node:
        case ast.Expr(value=value) | ast.keyword(arg="doc", value=value):
            return value if _is_text(value) else None
    return None


def _column(lines: list[str], row: int, offset: int) -> int:
    """The character column of a UTF-8 byte offset, as `ast` reports columns."""
    return len(lines[row - 1].encode()[:offset].decode(errors="ignore"))


def _span(lines: list[str], node: ast.expr) -> Span:
    end_row = node.end_lineno or node.lineno
    end_offset = node.end_col_offset or 0
    return (
        (node.lineno, _column(lines, node.lineno, node.col_offset)),
        (end_row, _column(lines, end_row, end_offset)),
    )


def documentation_spans(lines: list[str]) -> list[Span]:
    """The spans of a Starlark source's documentation strings, in order."""
    nodes = filter(None, map(_documentation, ast.walk(ast.parse("".join(lines)))))
    return sorted(_span(lines, node) for node in nodes)


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
    """
    The Starlark lines with their documentation strings cut, and each line's origin.

    A source that does not parse keeps its documentation, with a warning.
    """
    try:
        spans = documentation_spans(lines)
    except (SyntaxError, ValueError) as error:
        print(f"warning: {path}: documentation kept: {error}", file=sys.stderr)
        spans = []
    return cut_spans(lines, spans)
