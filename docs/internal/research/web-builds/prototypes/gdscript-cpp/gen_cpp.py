"""
Compile GDScript functions to C++ from their analyzed, typed syntax tree (prototype, C).

Reads the JSON that `dump_ast.gd` writes and emits `gdscript_native.gen.inc`, which the
runtime patch includes: one C++ function per GDScript function whose constructs this
prototype covers, plus a table the bytecode loader uses to run it instead of the bytecode.

What the types buy:
- statically typed locals and parameters are C++ values (`int64_t`, `double`, `bool`,
  `String`, `Vector2i`, `Array`, ...), and arithmetic on them is plain C++;
- members, also of other script instances whose class is static, are read and written in
  place through their index, typed members through `VariantInternal` without a check;
- calls to compiled script functions are direct C++ calls with typed arguments, and
  utility functions call `VariantUtilityFunctions` directly;
- everything without a static type stays a `Variant`, handled as the VM would.

A function with a construct the prototype does not cover is left out and runs as bytecode.
The modules: `cpp_types` (types and conversions), `cpp_model` (classes and functions),
`cpp_expressions` and `cpp_statements` (the code).

Usage: python3 gen_cpp.py <syntax tree dir> <output .inc> [script path prefix ...]
       [--godot <source>]   (with Godot's sources: engine calls go direct)
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cpp_engine
from cpp_expressions import typed
from cpp_implicit import implicit_functions
from cpp_model import Function, Klass, Program, function_symbol, signature
from cpp_statements import suite
from cpp_types import Unsupported, c_type, convert, gd_type

Parts = tuple[list[str], list[str], list[str]]


def compile_function(klass: Klass, node: dict) -> list[str]:
    if node["coroutine"] or node["vararg"]:
        raise Unsupported("coroutine or vararg function")
    fn = Function(klass, node)
    for p in node["parameters"]:
        fn.locals[p["name"]] = gd_type(p["type"])
    fn.emit("Variant *p_members = GDScriptNative::members(p_self);")
    suite(fn, node["body"])
    result = gd_type(node["return"])
    if result != "void":
        fn.emit(f"return {c_type(result)}();")  # Falling off the end returns the default.
    return [signature(klass, node) + " {", *fn.lines, "}"]


def _argument(klass: Klass, node: dict, index: int) -> str:
    """The entry's line that takes an argument, or its default."""
    p = node["parameters"][index]
    default = "Variant()"
    if p["initializer"] is not None:
        default = typed(Function(klass, node), p["initializer"], "Variant")
    return f"\tconst Variant a_{index} = p_argcount > {index} ? *p_args[{index}] : {default};"


def entry(klass: Klass, node: dict) -> list[str]:
    """The Variant entry the runtime calls: arguments and defaults to typed C++ values."""
    name = function_symbol(klass, node["name"])
    lines = [
        f"static Variant {name}_entry(GDScriptInstance *p_self, const Variant **p_args, int p_argcount, Callable::CallError &r_err) {{",
        "\tr_err.error = Callable::CallError::CALL_OK;",
    ]
    lines += [_argument(klass, node, i) for i in range(len(node["parameters"]))]
    values = [
        convert(f"a_{i}", "Variant", gd_type(p["type"]))
        for i, p in enumerate(node["parameters"])
    ]
    call = f"{name}({', '.join(['p_self', *values])})"
    result = gd_type(node["return"])
    if result == "void":
        return [*lines, f"\t{call};", "\treturn Variant();", "}"]
    return [*lines, f"\treturn {convert(call, result, 'Variant')};", "}"]


def load_class(tree: dict, program: Program) -> list[Klass]:
    """The class of a syntax tree and its inner classes, registered in program."""
    types = {
        m["name"]: gd_type(m["type"])
        for m in tree["members"]
        if m.get("node") == "variable"
    }
    functions = {m["name"]: m for m in tree["members"] if m.get("node") == "function"}
    variables = [m for m in tree["members"] if m.get("node") == "variable"]
    functions.update(
        {f["name"]: f for f in implicit_functions(variables, tree["member_indices"])}
    )
    inner = [
        k
        for m in tree["members"]
        if m.get("node") == "class"
        for k in load_class(m, program)
    ]
    symbol = "gd_" + re.sub(
        r"\W", "_", tree["fqcn"].removeprefix("res://").replace(".gd", "")
    )
    native = tree.get("native", "")
    klass = Klass(
        tree["fqcn"], tree["member_indices"], types, functions, symbol, program, native
    )
    program.classes[klass.fqcn] = klass
    return [klass, *inner]


def compile_class(klass: Klass, report: list[str]) -> Parts:
    """Declarations, definitions and table rows of a class's compilable functions."""
    declarations, definitions, rows = [], [], []
    for name, node in klass.functions.items():
        try:
            body = compile_function(klass, node)
            wrapper = entry(klass, node)
        except Unsupported as error:
            klass.program.compiled.discard((klass.fqcn, name))
            report.append(f"  bytecode  {klass.fqcn}.{name}: {error}")
            continue
        report.append(f"  C++       {klass.fqcn}.{name}")
        declarations.append(signature(klass, node) + ";")
        definitions += [*body, *wrapper]
        rows.append(
            f'\t{{ "{klass.fqcn}", "{name}", &{function_symbol(klass, name)}_entry }},'
        )
    return declarations, definitions, rows


def compile_program(program: Program, targets: list[Klass]) -> tuple[list[str], Parts]:
    """Compile until the set of compiled functions is stable: a direct call needs its
    target compiled, so a target that fails turns its callers' calls dynamic."""
    program.compiled = {(k.fqcn, name) for k in targets for name in k.functions}
    while True:
        before = set(program.compiled)
        report: list[str] = []
        parts: Parts = ([], [], [])
        for klass in targets:
            for part, lines in zip(parts, compile_class(klass, report), strict=True):
                part += lines
        if program.compiled == before:
            return report, parts


def generate(
    trees: Path, out: Path, prefixes: list[str], godot: Path | None = None
) -> None:
    program = Program(engine=cpp_engine.index(godot) if godot else None)
    for path in sorted(trees.rglob("*.json")):
        load_class(json.loads(path.read_text()), program)
    targets = [
        k
        for k in program.classes.values()
        if not prefixes or any(k.fqcn.startswith(p) for p in prefixes)
    ]
    report, (declarations, definitions, rows) = compile_program(program, targets)
    lines = [
        "// Generated by gen_cpp.py: GDScript functions compiled to C++.",
        '#include "gdscript_native.h"',
        "",
        *declarations,
        "",
        *definitions,
        "",
        "static const GDScriptNativeEntry gdscript_native_table[] = {",
        *rows,
        "\t{ nullptr, nullptr, nullptr },",
        "};",
    ]
    if program.engine:
        headers = program.engine.headers(program.used_classes)
        lines[2:2] = [f'#include "{header}"' for header in headers]
    out.write_text("\n".join(lines) + "\n")
    _write_usage(out, program, "\n".join(lines))
    print("\n".join(report))
    print(f"{len(rows)} functions compiled to C++")


def _write_usage(out: Path, program: Program, code: str) -> None:
    """Next to the output, what the compiled code still needs by name: the functions it
    replaces (their bytecode no longer runs) and every name it looks up at run time."""
    usage = {
        "compiled": sorted(f"{fqcn}.{name}" for fqcn, name in program.compiled),
        "names": sorted(set(re.findall(r'SNAME\("(\w+)"\)', code))),
        "direct": sorted(program.direct),
        "operators": sorted(program.operators),
    }
    out.with_suffix(".usage.json").write_text(json.dumps(usage, indent=1))


def main() -> None:
    args = sys.argv[1:]
    godot = None
    if "--godot" in args:
        at = args.index("--godot")
        godot = Path(args[at + 1])
        del args[at : at + 2]
    generate(Path(args[0]), Path(args[1]), args[2:], godot)


if __name__ == "__main__":
    main()
