"""
Remove the Variant built-in methods and utility functions a project does not use.

Like `shake_bindings.py` for `core/variant/variant_call.cpp` and `variant_utility.cpp`: a
registration stays when the bytecode calls it (`bytecode_usage.py`'s `builtin_methods` and
`utilities`) or its name is in a function's name table, since GDScript calls methods of
untyped values by name. Rewrites the files in place; restore the sources with git.

Usage: python3 shake_variant.py <godot source> <usage.json>
"""

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

# A built-in method's registration: `bind_<kind>(Type, name, ...);` or, for String's own
# macros, `bind_string_<kind>(name, ...);`. A utility function's: `FUNCBIND<kind>(name, ...);`.
_BUILTIN = re.compile(r"^\t(bind_[a-z_]+)\((\w+), (\w+)[,)].*\);$", re.MULTILINE)
_UTILITY = re.compile(r"^\t(FUNC[A-Z]+)\((\w+),.*\);$", re.MULTILINE)


def _rewrite(
    path: Path, pattern: re.Pattern[str], removable: Callable[[re.Match[str]], bool]
) -> tuple[int, int]:
    """Comment out the statements of pattern in path that removable accepts."""
    text = path.read_text()
    found = removed = 0

    def replace(statement: re.Match[str]) -> str:
        nonlocal found, removed
        found += 1
        if not removable(statement):
            return statement.group(0)
        removed += 1
        return "\t// Shaken: " + statement.group(0).strip()

    path.write_text(pattern.sub(replace, text))
    return found, removed


def _shake_variant(source: Path, usage: dict[str, list[str]], names: set[str]) -> None:
    """Remove the built-in methods and utility functions the bytecode does not call."""
    builtins = {entry.split(".", 1)[1] for entry in usage["builtin_methods"]} | names
    utilities = set(usage["utilities"]) | names

    def builtin_removable(statement: re.Match[str]) -> bool:
        string_macro = statement.group(1).startswith("bind_string_")
        name = statement.group(2) if string_macro else statement.group(3)
        # The last line of a macro definition binds its parameters, not a method.
        return not name.startswith("m_") and name not in builtins

    found, removed = _rewrite(
        source / "core/variant/variant_call.cpp", _BUILTIN, builtin_removable
    )
    print(f"built-in methods: {found} found, {removed} removed")
    found, removed = _rewrite(
        source / "core/variant/variant_utility.cpp",
        _UTILITY,
        lambda statement: statement.group(2) not in utilities,
    )
    print(f"utility functions: {found} found, {removed} removed")


def main() -> None:
    usage = json.loads(Path(sys.argv[2]).read_text())
    _shake_variant(Path(sys.argv[1]), usage, set(usage["names"]))


if __name__ == "__main__":
    main()
