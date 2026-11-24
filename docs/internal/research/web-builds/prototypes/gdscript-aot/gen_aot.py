"""
Specialize Godot's GDScript VM for a project's bytecode (prototype, stage B).

Every instruction of every function becomes a copy of its opcode's body from
`gdscript_vm.cpp`, behind its own label inside `GDScriptFunction::call()`. The copies read
`aot_ip`, a local whose address never escapes, set to the instruction's literal address,
and `_code_ptr` names a constant copy of the function's code, so the compiler folds
operand reads, stack addresses and jump targets into constants. `DISPATCH_OPCODE` jumps to
a switch from `aot_ip` to the function's labels, which a constant `aot_ip` reduces to a
direct jump. A function whose code equals a copy at load time starts there; any other runs
in the interpreter, and so does an instruction whose body could not be copied.

Writes three includes, for the directory of `gdscript_vm.cpp`:
- `gdscript_aot_data.gen.inc`: the code copies (file scope).
- `gdscript_aot_entry.gen.inc`: the jump into a specialized function (before the loop).
- `gdscript_aot_body.gen.inc`: the specialized instructions (inside the opcode switch).

Release builds only: the copies use the release definitions of the VM's operand macros.

Usage: python3 gen_aot.py <godot source> <bytecode dir> <output dir>
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import opcodes
import read_bytecode

_SWITCH = "OPCODE_SWITCH(_code_ptr[ip]) {"
_LABEL = re.compile(r"OPCODE\((OPCODE_\w+)\)")
_MACRO_USE = re.compile(
    r"^[ \t]*(OPCODE_ITERATE_BEGIN_PACKED_ARRAY|OPCODE_ITERATE_PACKED_ARRAY|OPCODE_TYPE_ADJUST)"
    r"\((\w+)[^;]*\);[ \t]*$",
    re.MULTILINE,
)
_MACRO_OPCODE = {
    "OPCODE_ITERATE_BEGIN_PACKED_ARRAY": "OPCODE_ITERATE_BEGIN_PACKED_{}_ARRAY",
    "OPCODE_ITERATE_PACKED_ARRAY": "OPCODE_ITERATE_PACKED_{}_ARRAY",
    "OPCODE_TYPE_ADJUST": "OPCODE_TYPE_ADJUST_{}",
}
_DEFINE = re.compile(r"^#define (\w+)(?:[^\n]*\\\n)*[^\n]*", re.MULTILINE)
_WRITES_CODE = re.compile(r"&_code_ptr\[|_code_ptr\[[^\]]*\]\s*=[^=]")
_IP = re.compile(r"(?<![\w.>])ip\b")
_OPERAND_MACROS = ("GET_VARIANT_PTR", "LOAD_INSTRUCTION_ARGS")
# The interpreter's own definitions, restored after the specialized code.
_INTERPRETER = {
    "OPCODE": "#define OPCODE(m_op) m_op:",
    "OPCODE_BREAK": "#define OPCODE_BREAK goto OPSEXIT",
    "OPCODE_OUT": "#define OPCODE_OUT goto OPSOUT",
    "DISPATCH_OPCODE": "#define DISPATCH_OPCODE goto *switch_table_ops[_code_ptr[ip]]",
}
_SPECIALIZED = {
    "OPCODE": "#define OPCODE(m_op)",
    "OPCODE_BREAK": "#define OPCODE_BREAK do { aot_real_ip = aot_ip; goto OPSEXIT; } while (0)",
    "OPCODE_OUT": "#define OPCODE_OUT do { aot_real_ip = aot_ip; goto OPSOUT; } while (0)",
}


def _define_name(definition: str) -> str:
    match = _DEFINE.match(definition)
    assert match, definition
    return match.group(1)


def _own_ip(source: str) -> str:
    """source with the VM's `ip` replaced by the specialized code's `aot_ip`."""
    return _IP.sub("aot_ip", source)


def _redefine(name: str, definition: str) -> list[str]:
    return [f"#undef {name}", definition]


def _switch(vm: str) -> str:
    """The opcode switch's body, without the include of the generated body."""
    start = vm.index(_SWITCH) + len(_SWITCH)
    end = vm.index("#if 0 // Enable for debugging.")
    hook = vm.find('#ifdef GDSCRIPT_AOT\n#include "gdscript_aot_body.gen.inc"', start)
    return vm[start : hook if 0 <= hook < end else end]


def _balanced(region: str) -> bool:
    """Whether region's preprocessor conditionals all close inside it."""
    depth = 0
    for line in region.splitlines():
        directive = line.strip()
        depth += directive.startswith("#if") - directive.startswith("#endif")
        if depth < 0:
            return False
    return depth == 0


def _tokens(switch: str) -> list[tuple[int, int, str, bool]]:
    """Opcode labels and macro uses in order: start, end, opcode, whether a macro use."""
    tokens = [(m.start(), m.end(), m.group(1), False) for m in _LABEL.finditer(switch)]
    tokens += [
        (m.start(), m.end(), _MACRO_OPCODE[m.group(1)].format(m.group(2)), True)
        for m in _MACRO_USE.finditer(switch)
    ]
    return sorted(tokens)


def opcode_bodies(vm: str) -> tuple[dict[str, str], list[str]]:
    """Opcode name -> the source that executes it, and the macro definitions it needs."""
    switch = _switch(vm)
    defines = [m.group(0) for m in _DEFINE.finditer(switch)]
    switch = re.sub(r"^#undef \w+\s*$", "", _DEFINE.sub("", switch), flags=re.MULTILINE)
    tokens = _tokens(switch)
    bodies: dict[str, str] = {}
    pending: list[str] = []
    for i, (start, end, name, is_macro) in enumerate(tokens):
        if is_macro:
            bodies[name] = switch[start:end]
            continue
        region = switch[end : tokens[i + 1][0] if i + 1 < len(tokens) else len(switch)]
        pending.append(name)
        if region.strip():  # Labels without a region share the next label's.
            bodies.update(dict.fromkeys(pending, region if _balanced(region) else ""))
            pending = []
    return bodies, defines


def _operand_macros(vm: str, own_ip: bool) -> list[str]:
    """The release definitions of the operand macros, reading aot_ip or ip."""
    head = vm[: vm.index(_SWITCH)]
    lines = []
    for name in _OPERAND_MACROS:
        definition = [m.group(0) for m in _DEFINE.finditer(head) if m.group(1) == name][
            -1
        ]
        lines += _redefine(name, _own_ip(definition) if own_ip else definition)
    return lines


def _c_array(values: list[int]) -> str:
    return "\n".join(
        "\t" + ", ".join(map(str, values[i : i + 24])) + ","
        for i in range(0, len(values), 24)
    )


class _Generator:
    def __init__(self, godot: Path) -> None:
        gd = godot / "modules/gdscript"
        self.vm = (gd / "gdscript_vm.cpp").read_text()
        self.names = opcodes.opcode_names((gd / "gdscript_function.h").read_text())
        self.lengths = opcodes.instruction_lengths(godot)
        self.bodies, self.defines = opcode_bodies(self.vm)
        self.specialized = self.fallback = 0

    def prologue(self) -> list[str]:
        lines = [
            "// Generated by gen_aot.py: specialized instructions.",
            "#ifdef DEBUG_ENABLED",
            "#error The GDScript AOT prototype supports release builds only.",
            "#endif",
        ]
        for name, definition in _SPECIALIZED.items():
            lines += _redefine(name, definition)
        lines += _operand_macros(self.vm, own_ip=True)
        for d in self.defines:
            lines += _redefine(_define_name(d), _own_ip(d))
        return [
            *lines,
            "aot_exit:",
            "\taot_real_ip = aot_ip;",
            "\tgoto *switch_table_ops[_code_ptr[aot_real_ip]];",
        ]

    def epilogue(self) -> list[str]:
        lines = []
        for name, definition in _INTERPRETER.items():
            lines += _redefine(name, definition)
        lines += _operand_macros(self.vm, own_ip=False)
        for d in self.defines:
            lines += _redefine(_define_name(d), d)
        return lines

    def instruction(self, index: int, ip: int, name: str) -> list[str]:
        label = f"aot_{index}_{ip}"
        source = self.bodies.get(name, "")
        if not source:
            self.fallback += 1
            return [f"{label}: aot_ip = {ip}; goto aot_exit;"]
        self.specialized += 1
        lines = [f"{label}: {{", f"\taot_ip = {ip};"]
        if _WRITES_CODE.search(source):
            return [*lines, _own_ip(source).rstrip(), "}"]
        return [
            *lines,
            f"#define _code_ptr aot_code_{index}",
            _own_ip(source).rstrip(),
            "#undef _code_ptr",
            "}",
        ]

    def function(self, index: int, f: read_bytecode.Function) -> list[str]:
        starts = opcodes.instructions(f.code, self.names, self.lengths)
        lines = [f"// {f.script} {f.klass}.{f.name}"]
        lines += _redefine(
            "DISPATCH_OPCODE", f"#define DISPATCH_OPCODE goto aot_{index}_dispatch"
        )
        lines += [f"aot_{index}_dispatch:", "\tswitch (aot_ip) {"]
        lines += [f"\t\tcase {ip}: goto aot_{index}_{ip};" for ip, _ in starts]
        lines += ["\t\tdefault: goto aot_exit;", "\t}"]
        for ip, name in starts:
            lines += self.instruction(index, ip, name)
        return lines


def _data(functions: list[read_bytecode.Function]) -> list[str]:
    lines = ["// Generated by gen_aot.py: code of the specialized functions."]
    for i, f in enumerate(functions):
        lines += [
            f"// {f.script} {f.klass}.{f.name}",
            f"static const int aot_code_{i}[] = {{\n{_c_array(f.code)}\n}};",
        ]
    count = len(functions)
    return [
        *lines,
        f"static const int *const aot_codes[] = {{ {', '.join(f'aot_code_{i}' for i in range(count))} }};",
        f"static const int aot_sizes[] = {{ {', '.join(str(len(f.code)) for f in functions)} }};",
        f"static constexpr int aot_count = {count};",
    ]


def _entry(count: int) -> list[str]:
    return [
        "// Generated by gen_aot.py: the jump into a specialized function.",
        "int aot_ip = ip; // Never escapes, unlike ip, so it stays a constant.",
        "int &aot_real_ip = ip;",
        "switch (_aot_index) {",
        *(f"\tcase {i}: goto aot_{i}_dispatch;" for i in range(count)),
        "\tdefault: break;",
        "}",
    ]


def generate(godot: Path, bytecode: Path, out: Path) -> None:
    generator = _Generator(godot)
    functions = read_bytecode.flatten(read_bytecode.functions(bytecode))
    body = generator.prologue()
    for index, f in enumerate(functions):
        body += generator.function(index, f)
    body += generator.epilogue()
    for name, lines in (
        ("data", _data(functions)),
        ("entry", _entry(len(functions))),
        ("body", body),
    ):
        (out / f"gdscript_aot_{name}.gen.inc").write_text("\n".join(lines) + "\n")
    print(
        f"{len(functions)} functions, {generator.specialized} instructions specialized, "
        f"{generator.fallback} fall back"
    )


if __name__ == "__main__":
    generate(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
