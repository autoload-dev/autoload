"""
Direct calls of engine methods from compiled GDScript.

A call or property access whose engine method the dump resolved (`bind`, `property`)
becomes `GDScriptNative::direct(object, &Class::method, args...)`: a plain C++ call on
the member function pointer the class binds. Arguments with a static C++ type go to the
method as they are, others as Variants through the binder's `VariantCaster`, and the
result comes back in the type of the GDScript expression. The method needs no MethodBind
and no lookup by name. Missing arguments take the binding's default values. Methods that
are not public, vararg, or whose defaults the generator cannot write stay calls by name.
"""

import json
from dataclasses import dataclass

from cpp_model import Function
from cpp_types import Unsupported, c_type, convert, literal

Typed = tuple[str, str]  # C++ code and the generator's type.


def _argument(code: str, gd: str) -> str:
    """An argument as C++: typed values as they are, everything else as a Variant."""
    return convert(code, gd, "Variant") if c_type(gd) == "Variant" else code


def _defaults(bind: dict, given: int) -> list[str] | None:
    """The default values for the arguments a call leaves out, or None if it cannot."""
    missing = bind["argcount"] - given
    defaults = bind["defaults"]
    if missing < 0 or missing > len(defaults):
        return None
    try:
        return [_argument(*literal(d)) for d in defaults[len(defaults) - missing :]]
    except Unsupported:
        return None


def _pointer(fn: Function, klass: str, method: str) -> tuple[str, bool] | None:
    engine = fn.program.engine
    binding = engine.binding(klass, method) if engine and klass else None
    if not binding:
        return None
    fn.program.used_classes.add(binding.owner)
    return binding.pointer, binding.static


def _typed(code: str, result: str) -> str:
    """A direct call's result in the type of the expression."""
    return code if result == "void" else f"GDScriptNative::to<{c_type(result)}>({code})"


def _args(values: list[str]) -> str:
    return "".join(f", {v}" for v in values)


@dataclass
class Receiver:
    """The object a direct call goes to (None for static methods) and its engine class."""

    fn: Function
    code: str | None
    klass: str = ""


def _resolve(
    receiver: Receiver, bind: dict, method: str, given: int
) -> tuple[str, bool, list[str]] | None:
    """The member function pointer of a call, whether it is static, and the default
    values its left-out arguments take; None if the call cannot go direct."""
    found = _pointer(receiver.fn, bind["class"], method)
    defaults = _defaults(bind, given)
    if not found or defaults is None:
        return None
    pointer, static = found
    return None if receiver.code is None and not static else (pointer, static, defaults)


def call(receiver: Receiver, node: dict, args: list[Typed], result: str) -> str | None:
    """A direct call of the engine method a call node resolved to, in the type result."""
    bind = node.get("bind") or {"vararg": True}
    resolved = (
        None if bind["vararg"] else _resolve(receiver, bind, node["function"], len(args))
    )
    if not resolved:
        return None
    pointer, static, defaults = resolved
    values = _args([*(_argument(*a) for a in args), *defaults])
    receiver.fn.program.direct.add(f"{bind['class']}.{node['function']}")
    if static:
        return _typed(f"GDScriptNative::direct_static({pointer}{values})", result)
    return _typed(f"GDScriptNative::direct({receiver.code}, {pointer}{values})", result)


def _accessor(receiver: Receiver, prop: dict, which: str) -> tuple[str, list[str]] | None:
    found = _pointer(receiver.fn, receiver.klass, prop.get(which, ""))
    if not found or found[1]:
        return None
    index = [f"int64_t({prop['index']})"] if prop.get("index", -1) != -1 else []
    receiver.fn.program.direct.add(f"{receiver.klass}.{prop[which]}")
    return found[0], index


def get(receiver: Receiver, prop: dict | None, result: str) -> str | None:
    """A property read through its getter, in the type result."""
    found = _accessor(receiver, prop or {}, "getter")
    if not found:
        return None
    pointer, index = found
    return _typed(
        f"GDScriptNative::direct({receiver.code}, {pointer}{_args(index)})", result
    )


def set_(receiver: Receiver, prop: dict | None, value: Typed) -> str | None:
    """A property write through its setter, as a statement."""
    found = _accessor(receiver, prop or {}, "setter")
    if not found:
        return None
    pointer, index = found
    return f"GDScriptNative::direct({receiver.code}, {pointer}{_args([*index, _argument(*value)])});"


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
