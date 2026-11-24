"""
What compiled GDScript needs to call engine methods directly: for each method a class
binds with `ClassDB::bind_method()`, the member function pointer it binds, and for each
class its header, namespace, parent and public methods.

A direct call takes the pointer's address in generated code, so the method must be
public; methods a class binds from its protected or private part stay calls by name.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

_DIRECTORIES = ("core", "scene", "servers", "modules", "drivers", "platform/web", "main")
_GDCLASS = re.compile(r"\bGDCLASS\((\w+),\s*([\w:]+)\)")
_NAMESPACE = re.compile(r"^namespace (\w+) \{", re.MULTILINE)
_ACCESS = re.compile(r"^\s*(public|protected|private):")
_DECLARED = re.compile(r"(\w+)\s*\(")
_NOT_METHODS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "GDVIRTUAL0",
    "operator",
}
_BIND_METHODS = re.compile(r"^void (\w+)::_bind_methods\(\) \{$", re.MULTILINE)
_BIND = re.compile(r"ClassDB::bind_(method|static_method)\(")
_NAME = re.compile(r'D_METHOD\("(\w+)"')
_POINTER_CLASS = re.compile(r"&(\w+)::")
_POINTER_OWNER = re.compile(r"&(?:\w+::)*?(\w+)::\w+$")


@dataclass
class EngineClass:
    name: str
    parent: str
    header: str
    qualified: str
    public: set[str] = field(default_factory=set)


@dataclass
class Binding:
    klass: str
    pointer: str
    static: bool

    @property
    def owner(self) -> str:
        """The class the member function pointer names."""
        match = _POINTER_OWNER.search(self.pointer)
        return match.group(1) if match else ""


@dataclass
class Engine:
    classes: dict[str, EngineClass] = field(default_factory=dict)
    bindings: dict[tuple[str, str], Binding] = field(default_factory=dict)

    def ancestors(self, name: str) -> list[str]:
        out = []
        while name in self.classes and name not in out:
            out.append(name)
            name = self.classes[name].parent
        return out

    def binding(self, klass: str, method: str) -> Binding | None:
        """The binding a class or its nearest ancestor makes of a method, if callable."""
        for name in self.ancestors(klass):
            found = self.bindings.get((name, method))
            if found:
                return found if self._reachable(found, method) else None
        return None

    def _reachable(self, binding: Binding, method: str) -> bool:
        owner = _POINTER_OWNER.search(binding.pointer)
        if not owner or binding.pointer.startswith("static_cast"):
            return False
        if binding.pointer.rsplit("::", 1)[-1].startswith("_"):
            return False  # Binding helpers like `_get_bind` are private as a rule.
        return any(
            method in self.classes[c].public for c in self.ancestors(owner.group(1))
        )

    def headers(self, classes: set[str]) -> list[str]:
        return sorted({self.classes[c].header for c in classes if c in self.classes})


def _matching(text: str, start: int) -> int:
    """The index just past the brace that closes the one at start."""
    depth = 0
    for i in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return i + 1
    return len(text)


def _namespace(text: str, position: int) -> str:
    for match in _NAMESPACE.finditer(text):
        if match.start() < position < _matching(text, match.end() - 1):
            return match.group(1) + "::"
    return ""


def _public_methods(body: str, access: str = "protected") -> set[str]:
    """The names declared in a class body's public parts, at class level; by default
    the body starts after GDCLASS, which ends in a protected part."""
    depth, names = 0, set()
    for line in body.splitlines():
        label = _ACCESS.match(line)
        if label and depth == 0:
            access = label.group(1)
        elif depth == 0 and access == "public":
            declared = _DECLARED.search(line)
            if declared and declared.group(1) not in _NOT_METHODS:
                names.add(declared.group(1))
        depth += line.count("{") - line.count("}")
    return names


def _index_header(engine: Engine, path: Path, root: Path) -> None:
    text = path.read_text(errors="replace")
    for match in _GDCLASS.finditer(text):
        name, parent = match.groups()
        opening = text.rfind("{", 0, match.start())
        body = text[match.end() : _matching(text, opening) - 1]
        engine.classes[name] = EngineClass(
            name,
            parent.split("::")[-1],
            str(path.relative_to(root)),
            _namespace(text, match.start()) + name,
            _public_methods(body),
        )


def _arguments(text: str, start: int) -> tuple[list[str], int]:
    """The top-level arguments of the call whose `(` is at start, and the end index."""
    depth, current, args = 0, start + 1, []
    for i in range(start, len(text)):
        depth += {"(": 1, ")": -1, "<": 0}.get(text[i], 0)
        if depth == 1 and text[i] == ",":
            args.append(text[current:i].strip())
            current = i + 1
        if depth == 0:
            args.append(text[current:i].strip())
            return args, i
    return args, len(text)


def _index_bindings(engine: Engine, text: str) -> None:
    for match in _BIND_METHODS.finditer(text):
        klass = match.group(1)
        body = text[match.end() - 1 : _matching(text, match.end() - 1)]
        for bind in _BIND.finditer(body):
            args, _ = _arguments(body, bind.end() - 1)
            static = bind.group(1) == "static_method"
            method, pointer = (args[1], args[2]) if static else (args[0], args[1])
            name = _NAME.search(method)
            if name and pointer.startswith(("&", "static_cast")):
                engine.bindings[(klass, name.group(1))] = Binding(klass, pointer, static)


def _index_object(engine: Engine, root: Path) -> None:
    """Object, the root, which has no GDCLASS."""
    text = (root / "core/object/object.h").read_text()
    opening = text.index("{", text.index("\nclass Object {"))
    body = text[opening + 1 : _matching(text, opening) - 1]
    engine.classes["Object"] = EngineClass(
        "Object", "", "core/object/object.h", "Object", _public_methods(body, "private")
    )


def index(root: Path) -> Engine:
    """The engine's classes and bindings, from its sources."""
    engine = Engine()
    _index_object(engine, root)
    for directory in _DIRECTORIES:
        for path in sorted((root / directory).rglob("*.h")):
            if "/tests/" not in str(path) and "/editor/" not in str(path):
                _index_header(engine, path, root)
        for path in sorted((root / directory).rglob("*.cpp")):
            text = path.read_text(errors="replace")
            if "_bind_methods()" in text:
                _index_bindings(engine, text)
    for binding in engine.bindings.values():
        binding.pointer = _qualify(engine, binding.pointer)
    return engine


def _qualify(engine: Engine, pointer: str) -> str:
    """The pointer with its class's namespace, as code outside the namespace needs it."""

    def qualified(match: re.Match[str]) -> str:
        klass = engine.classes.get(match.group(1))
        return f"&{klass.qualified if klass else match.group(1)}::"

    return _POINTER_CLASS.sub(qualified, pointer)
