"""
Direct calls of engine methods from compiled GDScript.

A call or property access whose engine method the dump resolved (`bind`, `property`)
becomes `GDScriptNative::invoke(object, &Class::method, {...})`: the binder's argument
conversion on the member function pointer the class binds, so the method needs no
MethodBind and no lookup by name. Missing arguments take the binding's default values.
Methods that are not public, vararg, or whose defaults the generator cannot write stay
calls by name.
"""

import json

from cpp_model import Function
from cpp_types import Unsupported, literal


def _defaults(bind: dict, given: int) -> list[str] | None:
    """The default values for the arguments a call leaves out, or None if it cannot."""
    missing = bind["argcount"] - given
    defaults = bind["defaults"]
    if missing < 0 or missing > len(defaults):
        return None
    try:
        values = [literal(d) for d in defaults[len(defaults) - missing :]]
    except Unsupported:
        return None
    return [code if gd == "Variant" else f"Variant({code})" for code, gd in values]


def _pointer(fn: Function, klass: str, method: str) -> tuple[str, bool] | None:
    engine = fn.program.engine
    binding = engine.binding(klass, method) if engine and klass else None
    if not binding:
        return None
    fn.program.used_classes.add(binding.owner)
    return binding.pointer, binding.static


def call(fn: Function, node: dict, receiver: str | None, values: list[str]) -> str | None:
    """A direct call of the engine method a call node resolved to, as a Variant."""
    bind = node.get("bind")
    if not bind or bind["vararg"]:
        return None
    found = _pointer(fn, bind["class"], node["function"])
    defaults = _defaults(bind, len(values))
    if not found or defaults is None:
        return None
    pointer, static = found
    args = ", ".join([*values, *defaults])
    fn.program.direct.add(f"{bind['class']}.{node['function']}")
    if static:
        return f"GDScriptNative::invoke_static({pointer}, {{ {args} }})"
    if receiver is None:
        return None
    return f"GDScriptNative::invoke({receiver}, {pointer}, {{ {args} }})"


def _accessor(
    fn: Function, klass: str, prop: dict, which: str
) -> tuple[str, list[str]] | None:
    found = _pointer(fn, klass, prop.get(which, ""))
    if not found or found[1]:
        return None
    index = [f"Variant(int64_t({prop['index']}))"] if prop.get("index", -1) != -1 else []
    fn.program.direct.add(f"{klass}.{prop[which]}")
    return found[0], index


def get(fn: Function, receiver: str, klass: str, prop: dict | None) -> str | None:
    """A property read through its getter, as a Variant."""
    found = _accessor(fn, klass, prop or {}, "getter")
    if not found:
        return None
    pointer, index = found
    return f"GDScriptNative::invoke({receiver}, {pointer}, {{ {', '.join(index)} }})"


def set_(
    fn: Function, receiver: str, klass: str, prop: dict | None, value: str
) -> str | None:
    """A property write through its setter, as a statement."""
    found = _accessor(fn, klass, prop or {}, "setter")
    if not found:
        return None
    pointer, index = found
    return f"GDScriptNative::invoke({receiver}, {pointer}, {{ {', '.join([*index, value])} }});"


def native_class(fn: Function, gd: str) -> str:
    """The engine class of a value: its native class, or a script class's native base."""
    if gd.startswith(("O:", "N:")):
        return gd[2:]
    if gd.startswith("C:"):
        klass = fn.program.classes.get(gd[2:])
        return klass.native if klass else ""
    return ""


def singleton(name: str) -> str:
    return f"GDScriptNative::native(SNAME({json.dumps(name)}))"
