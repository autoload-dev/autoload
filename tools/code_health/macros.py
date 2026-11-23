"""Finding the Bazel macros of a Starlark file, whose parameters mirror rule attributes.

A macro is a top-level function whose first parameter is `name` and that declares a
target with it (directly, or through a local variable derived from it), hands it to a
function that does, implements a symbolic macro, or documents `name:` as an argument and
returns nothing. Its parameters mirror the attributes of the rules it declares, so their
count is no more a smell than a rule's attribute count.
"""

from __future__ import annotations

import re

TOP_LEVEL_DEF = re.compile(r"^def\s+(\w+)\s*\(")


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
    """
    Table-driven macros declare their targets indirectly; they document `name`
    like a target and return nothing, unlike helpers that compute declarations.
    """
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
    """
    Whether a function body declares a target named after `name`, directly or through
    a local variable derived from it.
    """
    derived = set(DERIVED_NAME.findall(body)) - {"name"}
    return any(
        pattern.search(body)
        for pattern in [TARGET_NAME, *map(target_named_after, sorted(derived))]
    )


def macros_of(lines: list[str]) -> dict[str, int]:
    """
    Bazel macros: functions whose first parameter is `name` and that declare
    a target with it (`name = name...`), pass it on to another macro, or implement
    a symbolic macro. Returns each macro's def line index.
    """
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
