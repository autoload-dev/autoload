"""
GDScript opcodes and instruction lengths, derived from Godot's own sources.

The opcode numbers come from `enum Opcode` in `gdscript_function.h`. Each instruction's
length comes from `GDScriptFunction::disassemble()`, whose switch advances `ip` past every
instruction: the statements of a case that read operand counts (`instr_var_args`, `argc`,
`captures_count`) and set `incr` are translated to Python and run against the code.
"""

import re
from collections.abc import Callable
from pathlib import Path

Length = Callable[[list[int], int], int]

_STATEMENT = re.compile(
    r"^\s*(?:int (instr_var_args|argc|captures_count) = (.*);|incr (\+?=) (.*);)\s*$"
)
_CASE = re.compile(r"^\s*case (OPCODE_\w+):")
_MACRO_USE = re.compile(r"^\s*(DISASSEMBLE_\w+)\((\w+)\);")
_TYPES = re.compile(r"m_macro\((\w+)\)")
# Cases the disassembler writes through macros: opcode prefix and length.
_MACROS = {
    "DISASSEMBLE_ITERATE": ("OPCODE_ITERATE_", 5),
    "DISASSEMBLE_ITERATE_BEGIN": ("OPCODE_ITERATE_BEGIN_", 5),
    "DISASSEMBLE_TYPE_ADJUST": ("OPCODE_TYPE_ADJUST_", 2),
}


def opcode_names(header: str) -> list[str]:
    """The opcode names in the order of their numbers."""
    body = header[header.index("enum Opcode {") : header.index("OPCODE_END") + 10]
    return re.findall(r"(OPCODE_\w+)", body)


def _python(statement: tuple[str, str, str]) -> str:
    """One disassembler statement as Python over `code` and the position `pos`."""
    target, op, expression = statement
    expression = expression.replace("_code_ptr[++ip]", "code[_advance()]")
    expression = re.sub(r"\bip\b", "pos[0]", expression.replace("_code_ptr[", "code["))
    return f"{target} {op} {expression}"


def _fixed(size: int) -> Length:
    return lambda code, ip: size


def _length(statements: list[tuple[str, str, str]]) -> Length:
    """The length function of a case, from its statements."""
    program = compile("\n".join(map(_python, statements)), "<disassembler>", "exec")

    def length(code: list[int], start: int) -> int:
        pos = [start]

        def _advance() -> int:
            pos[0] += 1
            return pos[0]

        scope = {
            "code": code,
            "pos": pos,
            "_advance": _advance,
            "incr": 0,
            "_pointer_size": 2,
        }
        exec(program, scope)  # noqa: S102 - the statements are Godot's own disassembler's.
        return pos[0] - start + scope["incr"]

    return length


def _macro_cases(line: str, types: list[str]) -> dict[str, Length]:
    """The cases a disassembler macro use stands for, or none."""
    use = _MACRO_USE.match(line)
    if not use:
        return {}
    if use.group(1) == "DISASSEMBLE_ITERATE_TYPES":
        prefix, size = _MACROS[use.group(2)]
        return {prefix + t: _fixed(size) for t in types}
    if use.group(1) in _MACROS:
        prefix, size = _MACROS[use.group(1)]
        return {prefix + use.group(2): _fixed(size)}
    return {}


def _statement(line: str) -> tuple[str, str, str] | None:
    match = _STATEMENT.match(line)
    if not match:
        return None
    if match.group(1):
        return (match.group(1), "=", match.group(2))
    return ("incr", match.group(3), match.group(4))


class _Cases:
    """Collects the disassembler's cases: labels sharing a body, then its statements."""

    def __init__(self) -> None:
        self.lengths: dict[str, Length] = {}
        self.labels: list[str] = []
        self.statements: list[tuple[str, str, str]] = []
        self.in_body = False

    def label(self, name: str, opens_body: bool) -> None:
        if self.in_body:
            self.close()
        self.labels.append(name)
        self.in_body = self.in_body or opens_body

    def statement(self, statement: tuple[str, str, str]) -> None:
        if self.labels:
            self.in_body = True
            self.statements.append(statement)

    def close(self) -> None:
        if self.labels:
            fn = _length(self.statements)
            self.lengths.update(dict.fromkeys(self.labels, fn))
        self.labels, self.statements, self.in_body = [], [], False


def instruction_lengths(godot: Path) -> dict[str, Length]:
    """Opcode name -> function (code, ip) -> the instruction's length, for every opcode."""
    text = (godot / "modules/gdscript/gdscript_disassembler.cpp").read_text()
    types_start = text.index("#define DISASSEMBLE_ITERATE_TYPES")
    types = _TYPES.findall(text[types_start : text.index("\n\n", types_start)])
    cases = _Cases()
    for line in text[
        text.index("switch (opcode) {") : text.index("ip += incr;")
    ].splitlines():
        if line.lstrip().startswith("#") or line.rstrip().endswith("\\"):
            continue  # The disassembler's own macro definitions.
        case = _CASE.match(line)
        statement = _statement(line)
        if case:
            cases.label(case.group(1), "{" in line)
        elif statement:
            cases.statement(statement)
        else:
            cases.lengths.update(_macro_cases(line, types))
    cases.close()
    return cases.lengths


def instructions(
    code: list[int], names: list[str], lengths: dict[str, Length]
) -> list[tuple[int, str]]:
    """The (ip, opcode name) of every instruction of a function's code."""
    out = []
    ip = 0
    while ip < len(code):
        name = names[code[ip]]
        out.append((ip, name))
        ip += lengths[name](code, ip)
    return out
