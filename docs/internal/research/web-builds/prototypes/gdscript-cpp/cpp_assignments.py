"""C++ for GDScript assignments: to locals and members, dictionary keys, members of other
script instances, engine properties and components of engine properties."""

import json
from collections.abc import Callable

import cpp_native
from cpp_expressions import ARITHMETIC, OWNER, expression, foreign_member, typed
from cpp_model import Function
from cpp_types import NUMBERS, Unsupported, c_type, convert

_OPERATORS = {"+": "ADD", "-": "SUBTRACT", "*": "MULTIPLY", "/": "DIVIDE"}
_COMPONENTS = ("Vector2", "Vector2i", "Vector3", "Vector3i", "Color")


def _is_attribute(node: dict) -> bool:
    return node["node"] == "subscript" and "attribute" in node


def _property_value(fn: Function, node: dict, current: str | None) -> str:
    """The value a property assignment writes, compound operators applied to current."""
    value = typed(fn, node["value"], "Variant")
    op = node["operator"]
    if not op:
        return value
    if current is None or op not in _OPERATORS:
        raise Unsupported(f"compound assignment {op} to a property")
    return f"GDScriptNative::evaluate(Variant::OP_{_OPERATORS[op]}, {current}, {value})"


def _assign_property(fn: Function, node: dict, receiver: str, klass: str) -> bool:
    """A write through a property's setter, if the engine binds it."""
    prop = node["assignee"].get("property")
    current = cpp_native.get(fn, receiver, klass, prop)
    statement = cpp_native.set_(
        fn, receiver, klass, prop, _property_value(fn, node, current)
    )
    if statement:
        fn.emit(statement)
    return statement is not None


# Attribute targets: each strategy writes the assignment and says so, or leaves it.


def _assign_key(fn: Function, node: dict, base: str, bt: str) -> bool:
    if bt != "Dictionary" or node["operator"]:
        return False
    key = f"SNAME({json.dumps(node['assignee']['attribute'])})"
    fn.emit(f"{base}[{key}] = {typed(fn, node['value'], 'Variant')};")
    return True


def _is_script_member(fn: Function, bt: str, name: str) -> bool:
    return bt.startswith("C:") and name in fn.program.member(bt[2:], name)


def _assign_script_member(fn: Function, node: dict, base: str, bt: str) -> bool:
    name = node["assignee"]["attribute"]
    if node["operator"] or not _is_script_member(fn, bt, name):
        return False
    slot, gd = foreign_member(fn, base, bt[2:], name)
    fn.emit(f"{slot} = {typed(fn, node['value'], gd)};")
    return True


def _assign_component(fn: Function, node: dict, base: str, bt: str) -> bool:
    """`object.position.y = value`: read the property, change the component, write it."""
    holder = node["assignee"]["base"]
    if bt not in _COMPONENTS or node["operator"] or not _is_attribute(holder):
        return False
    outer, ot = expression(fn, holder["base"])
    receiver, klass = convert(outer, ot, "Variant"), cpp_native.native_class(fn, ot)
    temp = fn.fresh("value")
    setter = cpp_native.set_(
        fn, receiver, klass, holder.get("property"), f"Variant({temp})"
    )
    if not setter:
        return False
    component = "int" if bt.endswith("i") else "float"
    fn.emit(f"{c_type(bt)} {temp} = {base};")
    fn.emit(
        f"{temp}.{node['assignee']['attribute']} = {typed(fn, node['value'], component)};"
    )
    fn.emit(setter)
    return True


def _assign_engine_property(fn: Function, node: dict, base: str, bt: str) -> bool:
    receiver = convert(base, bt, "Variant")
    return _assign_property(fn, node, receiver, cpp_native.native_class(fn, bt))


_ATTRIBUTE_TARGETS: tuple[Callable[[Function, dict, str, str], bool], ...] = (
    _assign_key,
    _assign_script_member,
    _assign_component,
    _assign_engine_property,
)


def _assign_attribute(fn: Function, node: dict) -> None:
    base, bt = expression(fn, node["assignee"]["base"])
    if not any(target(fn, node, base, bt) for target in _ATTRIBUTE_TARGETS):
        raise Unsupported(f"attribute assignment on {bt}")


def _compound(fn: Function, node: dict, lhs: str, lt: str) -> None:
    op = node["operator"]
    rhs, rt = expression(fn, node["value"])
    if op not in ARITHMETIC or lt not in NUMBERS or rt not in NUMBERS:
        raise Unsupported(f"compound assignment {op} on {lt}")
    fn.emit(f"{lhs} {op}= {convert(rhs, rt, lt)};")


def assignment(fn: Function, node: dict) -> None:
    target = node["assignee"]
    if _is_attribute(target):
        _assign_attribute(fn, node)
        return
    if target.get("source") == "inherited_variable":
        if not _assign_property(fn, node, OWNER, fn.klass.native):
            raise Unsupported(f"assignment to {target['name']}")
        return
    lhs, lt = expression(fn, target)
    if node["operator"]:
        _compound(fn, node, lhs, lt)
        return
    fn.emit(f"{lhs} = {typed(fn, node['value'], lt)};")
    if lhs in fn.instances:
        fn.emit(f"{fn.instances[lhs]} = GDScriptNative::instance_or_null({lhs});")
