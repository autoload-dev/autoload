"""
A constant pool for the generated code. Written inline, every string literal, parsed
constant and `SNAME()` is a lambda with its own static and initialization guard. Pooled,
each distinct value is one entry of a table, and each use calls a shared lookup that
builds the value on first use and never frees it, like the VM's constants.
"""

import re
from dataclasses import dataclass

_QUOTED = r'("(?:[^"\\]|\\.)*")'


@dataclass(frozen=True)
class _Kind:
    name: str
    cpp_type: str
    # How the generator writes one use inline, with the quoted value as its group.
    inline: re.Pattern[str]
    # How the lookup builds a value from its entry `e`.
    build: str


_KINDS = (
    _Kind(
        "string",
        "String",
        re.compile(
            r"\(\[\]\(\) -> const String & \{ static const String \*value = "
            rf"new String\(String::utf8\({_QUOTED}\)\); return \*value; \}}\)\(\)"
        ),
        "new String(String::utf8(e))",
    ),
    _Kind(
        "constant",
        "Variant",
        re.compile(
            r"\(\[\]\(\) -> const Variant & \{ static const Variant \*value = "
            rf"new Variant\(GDScriptNative::constant\({_QUOTED}\)\); return \*value; \}}\)\(\)"
        ),
        "new Variant(GDScriptNative::constant(e))",
    ),
    _Kind(
        "name",
        "StringName",
        re.compile(rf"SNAME\({_QUOTED}\)"),
        "new StringName(e, true)",
    ),
)


def _lookup(kind: _Kind, entries: list[str]) -> list[str]:
    table = f"gd_{kind.name}_entries"
    return [
        f"static const char *const {table}[] = {{ {', '.join(entries)} }};",
        f"static _NO_INLINE_ const {kind.cpp_type} &gd_{kind.name}(int p_index) {{",
        f"\tstatic {kind.cpp_type} *pool[{len(entries)}] = {{}};",
        "\tif (!pool[p_index]) {",
        f"\t\tconst char *e = {table}[p_index];",
        f"\t\tpool[p_index] = {kind.build};",
        "\t}",
        "\treturn *pool[p_index];",
        "}",
    ]


def _pool_kind(kind: _Kind, code: str) -> tuple[list[str], str]:
    """The distinct values of one kind in code, in order, and code using their lookup."""
    entries: dict[str, int] = {}

    def use(match: re.Match[str]) -> str:
        index = entries.setdefault(match.group(1), len(entries))
        return f"gd_{kind.name}({index})"

    code = kind.inline.sub(use, code)
    return list(entries), code


def pool(code: str) -> tuple[list[str], str]:
    """The pool's tables and lookups, and code with every inline value replaced by a
    lookup."""
    lookups: list[str] = []
    for kind in _KINDS:
        entries, code = _pool_kind(kind, code)
        if entries:
            lookups += _lookup(kind, entries)
    return lookups, code
