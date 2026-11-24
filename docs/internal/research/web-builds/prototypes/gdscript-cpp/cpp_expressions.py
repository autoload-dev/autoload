"""C++ for GDScript expressions: each handler returns the code and its static type."""

import json
from collections.abc import Callable
from dataclasses import dataclass

import cpp_native
from cpp_model import Function, Klass, function_symbol
from cpp_types import (
    BUILTINS,
    NUMBERS,
    Unsupported,
    c_type,
    convert,
    gd_type,
    literal,
    truth,
)

Code = tuple[str, str]

_BINARY = {
    "+": "ADD", "-": "SUBTRACT", "*": "MULTIPLY", "/": "DIVIDE", "%": "MODULE",
    "<<": "SHIFT_LEFT", ">>": "SHIFT_RIGHT", "&": "BIT_AND", "|": "BIT_OR", "^": "BIT_XOR",
    "==": "EQUAL", "!=": "NOT_EQUAL", "<": "LESS", "<=": "LESS_EQUAL", ">": "GREATER",
    ">=": "GREATER_EQUAL", "in": "IN", "**": "POWER",
}  # fmt: skip
COMPARISONS = ("==", "!=", "<", "<=", ">", ">=")
ARITHMETIC = ("+", "-", "*", "/", "%")
_BITS = ("<<", ">>", "&", "|", "^")
_UTILITIES = {
    "absi", "absf", "maxi", "mini", "maxf", "minf", "clampi", "clampf", "sin", "cos",
    "move_toward", "lerpf", "posmod", "fposmod", "ceili", "pow",
}  # fmt: skip
_VARIANT_UTILITIES = {
    "print", "printerr", "prints", "printt", "print_rich", "push_error", "push_warning",
    "str", "is_instance_valid", "typeof", "randi", "randf", "randi_range", "randf_range",
    "var_to_str", "str_to_var", "hash", "is_same", "error_string",
}  # fmt: skip
_VECTORS = {
    "Vector2": ("real_t", 2),
    "Vector2i": ("int32_t", 2),
    "Vector3": ("real_t", 3),
    "Vector3i": ("int32_t", 3),
    "Color": ("float", 4),
}
_CONTAINERS = ("Array", "Dictionary")
# Fields of builtin value types that are plain C++ members, with their types.
FIELDS = {
    "Rect2": {"position": "Vector2", "size": "Vector2"},
    "Rect2i": {"position": "Vector2i", "size": "Vector2i"},
}
_CONTAINER_METHODS = {
    "append": "push_back", "push_back": "push_back", "clear": "clear", "size": "size",
    "is_empty": "is_empty", "get": "get", "has": "has", "remove_at": "remove_at",
}  # fmt: skip
_CONTAINER_RESULTS = {"size": "int", "is_empty": "bool", "has": "bool"}
_LOCALS = ("parameter", "local_variable", "local_iterator", "local_constant")
OWNER = "GDScriptNative::owner(p_self)"
# A method or signal of the script's object used as a value.
_SCRIPT_VALUES = {
    "member_function": ("method", "Callable"),
    "member_signal": ("signal", "Signal"),
}


def expression(fn: Function, node: dict) -> Code:
    """C++ for an expression node, with its type."""
    special = _inner_class(node) or _constant(node)
    if special:
        return special
    handler = _EXPRESSIONS.get(node["node"])
    if not handler:
        raise Unsupported(f"expression {node['node']}")
    return handler(fn, node)


def typed(fn: Function, node: dict, target: str) -> str:
    code, source = expression(fn, node)
    return convert(code, source, target)


def _inner_class(node: dict) -> Code | None:
    if node["node"] != "identifier" or node.get("source") != "member_class":
        return None
    fqcn = node["type"].get("class", "")
    return f"GDScriptNative::script_class({json.dumps(fqcn)})", f"M:{fqcn}"


def _constant(node: dict) -> Code | None:
    """A folded constant, or None to compile the expression itself."""
    constant = node.get("constant")
    if constant is None or node["node"] == "call":
        return None
    if constant["type"] == "Object" and constant["text"].startswith("res://"):
        # Loaded on use from the resource cache: a static would outlive the engine.
        return f"GDScriptNative::resource({json.dumps(constant['text'])})", gd_type(
            node["type"]
        )
    try:
        return literal(constant)
    except Unsupported:
        return None


# Names and members ------------------------------------------------------------------


def _slot(slot: str, gd: str) -> Code:
    """A member's Variant slot, typed members through VariantInternal."""
    if c_type(gd) == "Variant":
        return slot, gd
    return f"(*VariantInternal::{BUILTINS[gd][1]}(&{slot}))", gd


def _member(fn: Function, name: str) -> Code:
    index = fn.klass.member_indices.get(name)
    if index is None:
        raise Unsupported(f"member {name}")
    return _slot(f"p_members[{index}]", fn.klass.member_types.get(name, "Variant"))


def foreign_member(fn: Function, base: str, fqcn: str, name: str) -> Code:
    """A member of another script instance whose class is static."""
    klass = fn.program.classes[fqcn]
    slot = f"GDScriptNative::members({instance(fn, base)})[{klass.member_indices[name]}]"
    return _slot(slot, klass.member_types.get(name, "Variant"))


def instance(fn: Function, base: str) -> str:
    """The GDScript instance of a script-typed value, cached for locals."""
    return fn.instances.get(base) or f"GDScriptNative::instance({base})"


def _identifier(fn: Function, node: dict) -> Code:
    name, source = node["name"], node["source"]
    if source in _LOCALS:
        return f"l_{name}", fn.locals.get(name, gd_type(node["type"]))
    if source == "member_variable":
        return _member(fn, name)
    if source == "native_class":
        return f"GDScriptNative::native(SNAME({json.dumps(name)}))", f"N:{name}"
    if source in _SCRIPT_VALUES:
        function, gd = _SCRIPT_VALUES[source]
        return f"GDScriptNative::{function}(p_self, SNAME({json.dumps(name)}))", gd
    direct = None
    if source == "inherited_variable":
        direct = cpp_native.get(fn, OWNER, fn.klass.native, node.get("property"))
    if direct:
        return _result(direct, gd_type(node["type"]))
    raise Unsupported(f"identifier {name} ({source})")


def _literal(fn: Function, node: dict) -> Code:
    return literal(node["value"])


# Operators --------------------------------------------------------------------------


@dataclass
class _Operands:
    op: str
    left: str
    lt: str
    right: str
    rt: str
    result: str


def _logical(o: _Operands) -> Code | None:
    if o.op not in ("and", "or"):
        return None
    cpp = "&&" if o.op == "and" else "||"
    return f"({truth(o.left, o.lt)} {cpp} {truth(o.right, o.rt)})", "bool"


def _numeric(o: _Operands) -> Code | None:
    if o.lt not in NUMBERS or o.rt not in NUMBERS or o.op not in ARITHMETIC + COMPARISONS:
        return None
    if o.op == "%" and "float" in (o.lt, o.rt):
        return f"Math::fmod(double({o.left}), double({o.right}))", "float"
    return f"({o.left} {o.op} {o.right})", "bool" if o.op in COMPARISONS else o.result


def _bits(o: _Operands) -> Code | None:
    if o.lt == o.rt == "int" and o.op in _BITS:
        return f"({o.left} {o.op} {o.right})", "int"
    return None


def _comparison(o: _Operands) -> Code | None:
    if o.lt == o.rt and o.lt != "Variant" and o.op in COMPARISONS:
        return f"({o.left} {o.op} {o.right})", "bool"
    return None


def _variant_operator(o: _Operands) -> Code:
    left, right = convert(o.left, o.lt, "Variant"), convert(o.right, o.rt, "Variant")
    code = f"GDScriptNative::evaluate(Variant::OP_{_BINARY[o.op]}, {left}, {right})"
    return convert(code, "Variant", o.result) if o.result != "Variant" else code, o.result


def _binary(fn: Function, node: dict) -> Code:
    left, lt = expression(fn, node["left"])
    right, rt = expression(fn, node["right"])
    operands = _Operands(node["operator"], left, lt, right, rt, gd_type(node["type"]))
    for strategy in (_logical, _numeric, _bits, _comparison):
        found = strategy(operands)
        if found:
            return found
    return _variant_operator(operands)


def _unary(fn: Function, node: dict) -> Code:
    code, gd = expression(fn, node["operand"])
    op = node["operator"]
    if op == "not":
        return f"!{truth(code, gd)}", "bool"
    if gd in NUMBERS and op in ("-", "+"):
        return f"({op}{code})", gd
    if gd == "int" and op == "~":
        return f"(~{code})", "int"
    raise Unsupported(f"unary {op} on {gd}")


def _ternary(fn: Function, node: dict) -> Code:
    result = gd_type(node["type"])
    condition = truth(*expression(fn, node["condition"]))
    yes = typed(fn, node["true"], result)
    no = typed(fn, node["false"], result)
    return f"({condition} ? {c_type(result)}({yes}) : {c_type(result)}({no}))", result


# Subscripts -------------------------------------------------------------------------


@dataclass
class _Attribute:
    fn: Function
    node: dict
    base: str
    bt: str

    @property
    def name(self) -> str:
        return self.node["attribute"]

    @property
    def key(self) -> str:
        return f"SNAME({json.dumps(self.name)})"


def _component(a: _Attribute) -> Code | None:
    if a.bt in _VECTORS and len(a.name) == 1:
        return f"{a.base}.{a.name}", "int" if a.bt.endswith("i") else "float"
    if a.name in FIELDS.get(a.bt, {}):
        return f"{a.base}.{a.name}", FIELDS[a.bt][a.name]
    return None


def _builtin_method_value(a: _Attribute) -> Code | None:
    if a.bt not in BUILTINS or gd_type(a.node["type"]) != "Callable":
        return None
    return (
        f"GDScriptNative::bound_method({convert(a.base, a.bt, 'Variant')}, {a.key})",
        "Callable",
    )


def _dictionary_key(a: _Attribute) -> Code | None:
    if a.bt != "Dictionary":
        return None
    return f"GDScriptNative::get_key({a.base}, {a.key})", "Variant"


def _script_member(a: _Attribute) -> Code | None:
    if not a.bt.startswith("C:") or a.name not in a.fn.program.member(a.bt[2:], a.name):
        return None
    return foreign_member(a.fn, a.base, a.bt[2:], a.name)


def _engine_getter(a: _Attribute) -> Code | None:
    receiver, klass = (
        convert(a.base, a.bt, "Variant"),
        cpp_native.native_class(a.fn, a.bt),
    )
    direct = cpp_native.get(a.fn, receiver, klass, a.node.get("property"))
    return _result(direct, gd_type(a.node["type"])) if direct else None


def _attribute(fn: Function, node: dict, base: str, bt: str) -> Code:
    attribute = _Attribute(fn, node, base, bt)
    for strategy in (
        _component,
        _builtin_method_value,
        _dictionary_key,
        _script_member,
        _engine_getter,
    ):
        found = strategy(attribute)
        if found:
            return found
    return (
        f"GDScriptNative::get_named({convert(base, bt, 'Variant')}, {attribute.key})",
        "Variant",
    )


def _index(fn: Function, node: dict, base: str, bt: str) -> Code:
    index, it = expression(fn, node["index"])
    result = gd_type(node["type"])
    element = f"{base}[{index}]"
    if bt == "Array" and it == "int":
        code = (
            convert(element, "Variant", result)
            if result != "Variant"
            else f"Variant({element})"
        )
        return code, result
    code = f"GDScriptNative::get_indexed({convert(base, bt, 'Variant')}, {convert(index, it, 'Variant')})"
    return _result(code, result)


def _subscript(fn: Function, node: dict) -> Code:
    base, bt = expression(fn, node["base"])
    if "attribute" in node:
        return _attribute(fn, node, base, bt)
    return _index(fn, node, base, bt)


def _dictionary(fn: Function, node: dict) -> Code:
    items = []
    for key, value in node["pairs"]:
        items += [typed(fn, key, "Variant"), typed(fn, value, "Variant")]
    return f"GDScriptNative::dictionary({{ {', '.join(items)} }})", "Dictionary"


def element_type(t: dict) -> str:
    """A typed array's element type as `Variant::Type, class name, script` for C++."""
    kind = t.get("kind")
    if kind == "builtin" and t.get("builtin") in BUILTINS:
        return f"Variant::{BUILTINS[t['builtin']][2]}, StringName(), Variant()"
    if kind == "native":
        return f"Variant::OBJECT, SNAME({json.dumps(t['native'])}), Variant()"
    if kind in ("class", "script") and t.get("native"):
        script = (
            f"GDScriptNative::script_class({json.dumps(t.get('class') or t['script'])})"
        )
        return f"Variant::OBJECT, SNAME({json.dumps(t['native'])}), {script}"
    raise Unsupported(f"array of {kind}")


def _array(fn: Function, node: dict) -> Code:
    items = ", ".join(typed(fn, e, "Variant") for e in node["elements"])
    elements = node["type"].get("elements")
    if elements:
        return (
            f"GDScriptNative::typed_array({element_type(elements[0])}, {{ {items} }})",
            "Array",
        )
    return f"GDScriptNative::array({{ {items} }})", "Array"


def _get_node(fn: Function, node: dict) -> Code:
    return f"GDScriptNative::get_node(p_self, {json.dumps(node['path'])})", gd_type(
        node["type"]
    )


def _self(fn: Function, node: dict) -> Code:
    return OWNER, f"C:{fn.klass.fqcn}"


def _cast(fn: Function, node: dict) -> Code:
    code, gd = expression(fn, node["operand"])
    target = gd_type(node["type"])
    value = convert(code, gd, "Variant")
    if target.startswith("O:"):
        return (
            f"GDScriptNative::cast_native({value}, SNAME({json.dumps(target[2:])}))",
            target,
        )
    if target.startswith("C:"):
        return f"GDScriptNative::cast_script({value}, {json.dumps(target[2:])})", target
    return convert(code, gd, target), target


def _type_test(fn: Function, node: dict) -> Code:
    value = typed(fn, node["operand"], "Variant")
    test = gd_type({**node["test"], "hard": True, "meta": False})
    if test in BUILTINS:
        return f"(({value}).get_type() == Variant::{BUILTINS[test][2]})", "bool"
    if test.startswith(("O:", "N:")):
        return (
            f"GDScriptNative::is_native({value}, SNAME({json.dumps(test[2:])}))",
            "bool",
        )
    if test.startswith(("C:", "M:")):
        return f"GDScriptNative::is_script({value}, {json.dumps(test[2:])})", "bool"
    raise Unsupported(f"type test for {test}")


# Calls ------------------------------------------------------------------------------


@dataclass
class _Call:
    fn: Function
    name: str
    args: list[dict]
    result: str
    node: dict

    def variants(self) -> list[str]:
        return [typed(self.fn, a, "Variant") for a in self.args]


@dataclass
class _Target:
    """A script function's class, the instance it runs on and, for calls by name, the
    object to call."""

    klass: Klass
    instance: str
    base: str = ""


def _dynamic(base: str, name: str, values: list[str]) -> str:
    return f"GDScriptNative::call({base}, SNAME({json.dumps(name)}), {{ {', '.join(values)} }})"


def _result(code: str, result: str) -> Code:
    """A Variant-returning call as an expression of the call's static type."""
    if result == "void":
        return code, result
    return convert(code, "Variant", result), result


def _script_call(call: _Call, target: _Target) -> Code:
    """A call of a script function: direct when it is compiled, else through the runtime."""
    function = target.klass.functions[call.name]
    parameters = function["parameters"]
    compiled = (target.klass.fqcn, call.name) in call.fn.program.compiled
    if compiled and not function["static"] and len(call.args) == len(parameters):
        values = [
            typed(call.fn, a, gd_type(p["type"]))
            for a, p in zip(call.args, parameters, strict=True)
        ]
        symbol = function_symbol(target.klass, call.name)
        return f"{symbol}({', '.join([target.instance, *values])})", gd_type(
            function["return"]
        )
    owner = target.base or "GDScriptNative::owner(p_self)"
    return _result(_dynamic(owner, call.name, call.variants()), call.result)


def _own_function(call: _Call) -> Code | None:
    if call.name not in call.fn.klass.functions:
        return None
    return _script_call(call, _Target(call.fn.klass, "p_self"))


def _utility(call: _Call) -> Code | None:
    if call.name not in _UTILITIES:
        return None
    arg_type = "int" if call.name.endswith("i") or call.name == "posmod" else "float"
    values = [typed(call.fn, a, arg_type) for a in call.args]
    return f"VariantUtilityFunctions::{call.name}({', '.join(values)})", call.result


def _scalar_conversion(call: _Call) -> Code | None:
    if call.name not in ("int", "float", "bool") or len(call.args) != 1:
        return None
    code, gd = expression(call.fn, call.args[0])
    if gd == "String" and call.name != "bool":  # `int("42")` parses.
        return f"{code}.to_{call.name}()", call.name
    return convert(code, gd, call.name), call.name


def _vector(call: _Call) -> Code | None:
    if call.name not in _VECTORS or len(call.args) != _VECTORS[call.name][1]:
        return None
    component = _VECTORS[call.name][0]
    values = [
        typed(call.fn, a, "int" if component == "int32_t" else "float") for a in call.args
    ]
    return f"{call.name}({', '.join(f'{component}({v})' for v in values)})", call.name


def _construct(call: _Call) -> Code | None:
    if call.name not in BUILTINS or call.result != call.name:
        return None
    variant_type = BUILTINS[call.name][2]
    code = f"GDScriptNative::construct(Variant::{variant_type}, {{ {', '.join(call.variants())} }})"
    return convert(code, "Variant", call.name), call.name


def _unknown_constructor(call: _Call) -> Code | None:
    if call.name in BUILTINS or call.name == "Object":
        raise Unsupported(f"constructor {call.name}")  # Never a method of the script.
    return None


def _global_call(call: _Call) -> Code:
    strategies = (
        _own_function,
        _utility,
        _scalar_conversion,
        _vector,
        _construct,
        _unknown_constructor,
    )
    for strategy in strategies:
        found = strategy(call)
        if found:
            return found
    values = call.variants()
    if call.name in _VARIANT_UTILITIES:
        code = f"GDScriptNative::utility(SNAME({json.dumps(call.name)}), {{ {', '.join(values)} }})"
    else:  # A method the script inherits from its native class.
        code = cpp_native.call(call.fn, call.node, OWNER, values) or _dynamic(
            OWNER, call.name, values
        )
    return _result(code, call.result)


def _with_default(bt: str, name: str, values: list[str]) -> list[str]:
    """`Dictionary::get()` has no default argument in C++; GDScript's is null."""
    missing = bt == "Dictionary" and name == "get" and len(values) == 1
    return [*values, "Variant()"] if missing else values


def _container_method(call: _Call, base: str, bt: str, values: list[str]) -> Code | None:
    if bt not in _CONTAINERS or call.name not in _CONTAINER_METHODS:
        return None
    code = f"{base}.{_CONTAINER_METHODS[call.name]}({', '.join(_with_default(bt, call.name, values))})"
    if call.result in ("void", "Variant"):
        return code, call.result
    return convert(
        code, _CONTAINER_RESULTS.get(call.name, call.result), call.result
    ), call.result


def _native_class_call(call: _Call, klass: str, values: list[str]) -> Code:
    """`Class.new()`, a singleton's method or a static method of an engine class."""
    if call.name == "new" and not values:
        return _result(
            f"GDScriptNative::instantiate(SNAME({json.dumps(klass)}))", call.result
        )
    direct = cpp_native.call(call.fn, call.node, cpp_native.singleton(klass), values)
    if direct:
        return _result(direct, call.result)
    names = f"SNAME({json.dumps(klass)}), SNAME({json.dumps(call.name)})"
    return _result(
        f"GDScriptNative::call_native({names}, {{ {', '.join(values)} }})", call.result
    )


def _object_call(call: _Call, receiver: str, values: list[str]) -> Code:
    """A method of an object: direct when the engine binds it, else by name."""
    direct = cpp_native.call(call.fn, call.node, receiver, values)
    return _result(direct or _dynamic(receiver, call.name, values), call.result)


def _method_call(call: _Call, base_node: dict) -> Code:
    base, bt = expression(call.fn, base_node)
    if bt.startswith("C:") and call.name in call.fn.program.functions(bt[2:]):
        klass = call.fn.program.classes[bt[2:]]
        return _script_call(call, _Target(klass, instance(call.fn, base), base))
    values = call.variants()
    found = _container_method(call, base, bt, values)
    if found:
        return found
    if bt.startswith("N:"):
        return _native_class_call(call, bt[2:], values)
    return _object_call(call, convert(base, bt, "Variant"), values)


def _is_method(callee: dict | None, name: str) -> bool:
    return (
        bool(callee) and callee["node"] == "subscript" and callee.get("attribute") == name
    )


def _call(fn: Function, node: dict) -> Code:
    callee = node["callee"]
    call = _Call(fn, node["function"], node["arguments"], gd_type(node["type"]), node)
    if _is_method(callee, call.name):
        return _method_call(call, callee["base"])
    if callee and callee["node"] == "identifier":
        return _global_call(call)
    raise Unsupported(f"call of {call.name}")


_EXPRESSIONS: dict[str, Callable[[Function, dict], Code]] = {
    "identifier": _identifier,
    "literal": _literal,
    "binary": _binary,
    "unary": _unary,
    "ternary": _ternary,
    "subscript": _subscript,
    "call": _call,
    "dictionary": _dictionary,
    "array": _array,
    "self": _self,
    "get_node": _get_node,
    "cast": _cast,
    "type_test": _type_test,
}


def is_expression(node: dict) -> bool:
    return node["node"] in _EXPRESSIONS
