"""C++ for GDScript statements, emitted into the function being compiled."""

from collections.abc import Callable

from cpp_assignments import assignment
from cpp_expressions import expression, is_expression, typed
from cpp_model import Function
from cpp_types import BUILTINS, Unsupported, c_type, convert, gd_type, truth


def suite(fn: Function, node: dict | None) -> None:
    if node is None:
        return
    for statement in node["statements"]:
        handler = _STATEMENTS.get(statement["node"])
        if handler:
            handler(fn, statement)
        elif is_expression(statement):
            code, _ = expression(fn, statement)
            fn.emit(f"{code};")
        else:
            raise Unsupported(f"statement {statement['node']}")


def _block(
    fn: Function, header: str, body: dict | None, before: list[str] | None = None
) -> None:
    fn.emit(header + " {")
    fn.depth += 1
    for line in before or []:
        fn.emit(line)
    saved = dict(fn.locals)
    suite(fn, body)
    fn.locals = saved
    fn.depth -= 1
    fn.emit("}")


def _cache_instance(fn: Function, name: str, gd: str) -> list[str]:
    """Declares the instance cache of a script-typed local; lines to emit."""
    if not gd.startswith("C:"):
        return []
    fn.instances[f"l_{name}"] = f"li_{name}"
    return [f"GDScriptInstance *li_{name} = GDScriptNative::instance_or_null(l_{name});"]


# Declarations and control flow ------------------------------------------------------


def _variable(fn: Function, node: dict) -> None:
    gd = gd_type(node["type"])
    if gd == "void":
        raise Unsupported("void variable")
    name = node["name"]
    value = (
        typed(fn, node["initializer"], gd) if node["initializer"] else f"{c_type(gd)}()"
    )
    fn.emit(f"{c_type(gd)} l_{name} = {value};")
    fn.locals[name] = gd
    for line in _cache_instance(fn, name, gd):
        fn.emit(line)


def _if(fn: Function, node: dict) -> None:
    condition = truth(*expression(fn, node["condition"]))
    _block(fn, f"if ({condition})", node["then"])
    if node["else"]:
        _block(fn, "else", node["else"])


def _while(fn: Function, node: dict) -> None:
    condition = truth(*expression(fn, node["condition"]))
    _block(fn, f"while ({condition})", node["body"])


def _is_range(listing: dict) -> bool:
    callee = listing.get("callee") or {}
    return (
        listing["node"] == "call"
        and listing["function"] == "range"
        and callee.get("node") == "identifier"
    )


def _range_bounds(fn: Function, arguments: list[dict]) -> tuple[str, str, str]:
    bounds = [typed(fn, a, "int") for a in arguments]
    if len(bounds) == 1:
        return "0", bounds[0], "1"
    return bounds[0], bounds[1], bounds[2] if len(bounds) == 3 else "1"


def _for_range(fn: Function, node: dict) -> None:
    name = node["variable"]
    start, end, step = _range_bounds(fn, node["list"]["arguments"])
    end_var, step_var = fn.fresh("end"), fn.fresh("step")
    fn.emit(f"const int64_t {end_var} = {end};")
    fn.emit(f"const int64_t {step_var} = {step};")
    fn.locals[name] = "int"
    condition = f"({step_var} > 0 ? l_{name} < {end_var} : l_{name} > {end_var})"
    _block(
        fn,
        f"for (int64_t l_{name} = {start}; {condition}; l_{name} += {step_var})",
        node["body"],
    )


# Element types of the containers a `for` loop walks by index.
_ELEMENTS = {
    "Array": "Variant",
    "PackedByteArray": "int",
    "PackedInt32Array": "int",
    "PackedInt64Array": "int",
    "PackedFloat32Array": "float",
    "PackedFloat64Array": "float",
    "PackedStringArray": "String",
    "PackedVector2Array": "Vector2",
    "PackedVector3Array": "Vector3",
    "PackedColorArray": "Color",
}


def _for_container(fn: Function, node: dict) -> None:
    name = node["variable"]
    gd = gd_type(node["variable_type"])
    container, ct = expression(fn, node["list"])
    if ct not in _ELEMENTS:
        raise Unsupported(f"for over {ct}")
    holder, index = fn.fresh("list"), fn.fresh("i")
    fn.emit(f"const {BUILTINS[ct][0]} {holder} = {container};")
    item, element = f"{holder}[{index}]", _ELEMENTS[ct]
    fn.locals[name] = gd
    value = convert(item, element, gd) if gd != "Variant" else f"Variant({item})"
    loop = f"for (int64_t {index} = 0; {index} < {holder}.size(); {index}++)"
    _block(
        fn,
        loop,
        node["body"],
        [f"{c_type(gd)} l_{name} = {value};", *_cache_instance(fn, name, gd)],
    )


def _for(fn: Function, node: dict) -> None:
    if _is_range(node["list"]):
        _for_range(fn, node)
    else:
        _for_container(fn, node)


def _pattern(fn: Function, test: str, pattern: dict) -> str | None:
    """A literal or expression pattern as a condition on test; None for the wildcard."""
    if pattern["kind"] == "wildcard":
        return None
    if pattern["kind"] not in ("literal", "expression"):
        raise Unsupported(f"{pattern['kind']} pattern")
    return f"GDScriptNative::matches({test}, {typed(fn, pattern['value'], 'Variant')})"


def _match(fn: Function, node: dict) -> None:
    test = fn.fresh("match")
    fn.emit(f"const Variant {test} = {typed(fn, node['test'], 'Variant')};")
    keyword = "if"
    for branch in node["branches"]:
        if branch["guard"]:
            raise Unsupported("match guard")
        conditions = [_pattern(fn, test, p) for p in branch["patterns"]]
        if None in conditions:  # A wildcard takes whatever the branches before left.
            _block(fn, "else" if keyword != "if" else "if (true)", branch["body"])
            return
        _block(
            fn, f"{keyword} ({' || '.join(c for c in conditions if c)})", branch["body"]
        )
        keyword = "else if"


def _return(fn: Function, node: dict) -> None:
    gd = gd_type(fn.node["return"])
    if node["value"] is not None:
        fn.emit(f"return {typed(fn, node['value'], gd)};")
    else:
        fn.emit("return;" if gd == "void" else f"return {c_type(gd)}();")


def _pass(fn: Function, node: dict) -> None:
    pass


def _raw(fn: Function, node: dict) -> None:
    """Code the generator wrote itself, such as a member's default value."""
    fn.emit(node["code"])


def _continue(fn: Function, node: dict) -> None:
    fn.emit("continue;")


def _break(fn: Function, node: dict) -> None:
    fn.emit("break;")


_STATEMENTS: dict[str, Callable[[Function, dict], None]] = {
    "assignment": assignment,
    "variable": _variable,
    "if": _if,
    "while": _while,
    "for": _for,
    "match": _match,
    "return": _return,
    "pass": _pass,
    "continue": _continue,
    "raw": _raw,
    "break": _break,
}
