"""
Remove the Variant operator evaluators nothing can call.

`Variant::_register_variant_operators()` (`core/variant/variant_op.cpp`) registers an
evaluator for every operator on every pair of types that supports it, and each
registration keeps its evaluator's template instances alive. A registration stays when:

- the engine evaluates its operator on values of any type (`_ENGINE`): sorting, `min()`,
  `max()` and `clamp()` compare, hashing compares for equality, tweens add and subtract;
- the bytecode evaluates it (`bytecode_usage.py`'s `operators`);
- code compiled to C++ evaluates it at run time on operands whose static types match
  (`gen_cpp.py`'s `operators`, from `--compiled`; an untyped operand matches any type).

The engine's `Expression` class evaluates any operator, so the build profile must disable
it. Rewrites the file in place; restore the sources with git.

Usage: python3 shake_operators.py <godot source> <usage.json> [--compiled <usage.json>]
"""

import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

_ENGINE = {"EQUAL", "NOT_EQUAL", "LESS", "GREATER", "ADD", "SUBTRACT"}
_STRINGS = frozenset({"STRING", "STRING_NAME"})
# A registration statement, and its (innermost, last) argument list.
_STATEMENT = re.compile(r"^\t(register_\w+)\b.*\(([^()]*)\);$", re.MULTILINE)
_OBJECTS = ("C:", "O:", "M:", "N:")

Use = tuple[str, str | None, str | None]


def variant_type(gd: str) -> str | None:
    """The `Variant::Type` of a static GDScript type, or None for an untyped value."""
    if gd == "Variant":
        return None
    if gd.startswith(_OBJECTS):
        return "OBJECT"
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[0-9])(?=Array)", "_", gd).upper()


def _enum(header: str, name: str) -> list[str]:
    """The entries of a C++ enum in header, in order."""
    body = re.search(rf"enum {name} {{(.*?)}};", header, re.DOTALL)
    assert body, name
    text = re.sub(r"//[^\n]*", "", body.group(1))
    return [e.split("=")[0].strip() for e in text.split(",") if e.strip()]


def _bytecode_uses(source: Path, entries: Iterable[str]) -> set[Use]:
    """The bytecode's `operator:left:right` enum indices as uses."""
    header = (source / "core/variant/variant.h").read_text()
    operators, types = _enum(header, "Operator"), _enum(header, "Type")
    uses = set()
    for entry in entries:
        op, left, right = (int(i) for i in entry.split(":"))
        uses.add((operators[op].removeprefix("OP_"), types[left], types[right]))
    return uses


def _compiled_uses(entries: Iterable[list[str]]) -> set[Use]:
    return {(op, variant_type(left), variant_type(right)) for op, left, right in entries}


def _operands(kind: str, arguments: list[str]) -> tuple[str, set[str], set[str]]:
    """The operator and the possible left and right types of a registration."""
    if kind == "register_string_op":
        return arguments[0], set(_STRINGS), set(_STRINGS)
    if kind == "register_string_modulo_op":
        return "MODULE", set(_STRINGS), {arguments[0]}
    return arguments[0], {arguments[1]}, {arguments[2]}


def _kept(statement: re.Match[str], uses: set[Use]) -> bool:
    arguments = [
        a.removeprefix("OP_") for a in re.findall(r"Variant::(\w+)", statement.group(2))
    ]
    op, lefts, rights = _operands(statement.group(1), arguments)
    return op in _ENGINE or any(
        use_op == op
        and (left is None or left in lefts)
        and (right is None or right in rights)
        for use_op, left, right in uses
    )


def shake(source: Path, uses: set[Use]) -> tuple[int, int]:
    """Comment out the unused registrations; how many were found and removed."""
    path = source / "core/variant/variant_op.cpp"
    found = removed = 0

    def replace(statement: re.Match[str]) -> str:
        nonlocal found, removed
        found += 1
        if _kept(statement, uses):
            return statement.group(0)
        removed += 1
        return "\t// Shaken: " + statement.group(0).strip()

    path.write_text(_STATEMENT.sub(replace, path.read_text()))
    return found, removed


def main() -> None:
    source = Path(sys.argv[1])
    usage = json.loads(Path(sys.argv[2]).read_text())
    uses = _bytecode_uses(source, usage["operators"])
    if "--compiled" in sys.argv:
        compiled = Path(sys.argv[sys.argv.index("--compiled") + 1])
        uses |= _compiled_uses(json.loads(compiled.read_text())["operators"])
    found, removed = shake(source, uses)
    print(f"operators: {found} found, {removed} removed")


if __name__ == "__main__":
    main()
