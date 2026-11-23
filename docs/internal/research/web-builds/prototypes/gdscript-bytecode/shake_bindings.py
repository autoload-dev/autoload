"""
Remove the method bindings a project does not use from Godot's sources, before a build.

Every `ClassDB::bind_method`, `bind_static_method` and `bind_vararg_method` statement in a
class's `_bind_methods()` is removed unless its method is kept:

- the project's bytecode calls it (`bytecode_usage.py`'s `method_binds`), or it is listed
  in `--keep`;
- its name is the setter or getter of any property (`ADD_PROPERTY`), since scenes and
  resources set properties through them, and a class may use an accessor its parent binds;
- its name starts with `_`: the engine binds its own callbacks so it can call them by name;
- its name is in a function's name table (`names`): GDScript calls methods by name when it
  cannot resolve the method at compile time, such as `new()` on a native class.

The GDScript module's own bindings are never removed.

Without the binding, the method bind's template instance and often the method itself lose
their last reference, and the linker drops them. Rewrites the files in place; restore the
sources with git afterwards.

Usage: python3 shake_bindings.py <godot source> <usage.json> [--keep Class.method,...]
"""

import json
import re
import sys
from pathlib import Path

_BIND_METHODS = re.compile(r"^void (\w+)::_bind_methods\(\) \{$", re.MULTILINE)
_STATEMENT = re.compile(
    r"^(\t+)ClassDB::bind_(?:method|static_method|vararg_method)\([^;]*?\);[^\n]*\n",
    re.MULTILINE,
)
_NAME = re.compile(r'D_METHOD\("(\w+)"|bind_vararg_method\(\s*\w+,\s*"(\w+)"')
_PROPERTY = re.compile(
    r'ADD_PROPERTYI?\(\s*PropertyInfo\((?:[^;])*?\),\s*"(\w*)",\s*"(\w*)"'
)
_DIRECTORIES = ("core", "scene", "servers", "modules", "drivers", "platform/web", "main")


def _body_end(text: str, start: int) -> int:
    """The index just past the closing brace of the function body that opens at start."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _shake(
    text: str, keep: set[str], accessors: set[str], names: set[str]
) -> tuple[str, int, int]:
    """Return text without the unused bindings, and how many were found and removed."""
    found = removed = 0
    pieces = []
    last = 0
    for match in _BIND_METHODS.finditer(text):
        cls = match.group(1)
        start = match.end() - 1
        end = _body_end(text, start)
        body = text[start:end]

        def replace(statement: re.Match[str], cls: str = cls) -> str:
            nonlocal found, removed
            name_match = _NAME.search(statement.group(0))
            if not name_match:
                return statement.group(0)
            name = name_match.group(1) or name_match.group(2)
            found += 1
            if (
                name.startswith("_")
                or name in accessors
                or name in names
                or f"{cls}.{name}" in keep
            ):
                return statement.group(0)
            removed += 1
            return f"{statement.group(1)}// Shaken: {cls}.{name}\n"

        pieces.append(text[last:start])
        pieces.append(_STATEMENT.sub(replace, body))
        last = end
    pieces.append(text[last:])
    return "".join(pieces), found, removed


def main() -> None:
    source = Path(sys.argv[1])
    usage = json.loads(Path(sys.argv[2]).read_text())
    keep = set(usage["method_binds"])
    names = set(usage["names"])
    if "--keep" in sys.argv:
        keep |= set(sys.argv[sys.argv.index("--keep") + 1].split(","))
    files = [
        path
        for directory in _DIRECTORIES
        for path in sorted((source / directory).rglob("*.cpp"))
        if "/tests/" not in str(path)
        and "/editor/" not in str(path)
        and "modules/gdscript" not in str(path)
    ]
    texts = {path: path.read_text() for path in files}
    accessors = {
        name
        for text in texts.values()
        for pair in _PROPERTY.findall(text)
        for name in pair
        if name
    }
    total_found = total_removed = 0
    for path, text in texts.items():
        if "_bind_methods()" not in text:
            continue
        new_text, found, removed = _shake(text, keep, accessors, names)
        total_found += found
        total_removed += removed
        if removed:
            path.write_text(new_text)
    print(f"bindings: {total_found} found, {total_removed} removed")


if __name__ == "__main__":
    main()
