"""C++ for GDScript statements, emitted into the function being compiled."""

from collections.abc import Callable

from cpp_assignments import assignment
from cpp_expressions import expression, is_expression, typed
from cpp_model import Function
from cpp_types import Unsupported, c_type, convert, gd_type, truth


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


def _for_range(fn: Function, node: dict) -> None:
    name = node["variable"]
    bounds = [typed(fn, a, "int") for a in node["list"]["arguments"]]
    if len(bounds) not in (1, 2):
        raise Unsupported("range with a step")
    start, end = ("0", bounds[0]) if len(bounds) == 1 else (bounds[0], bounds[1])
    end_var = fn.fresh("end")
    fn.emit(f"const int64_t {end_var} = {end};")
    fn.locals[name] = "int"
    _block(
        fn,
        f"for (int64_t l_{name} = {start}; l_{name} < {end_var}; l_{name}++)",
        node["body"],
    )


def _for_container(fn: Function, node: dict) -> None:
    name = node["variable"]
    gd = gd_type(node["variable_type"])
    container, ct = expression(fn, node["list"])
    if ct not in ("Array", "PackedInt32Array"):
        raise Unsupported(f"for over {ct}")
    holder, index = fn.fresh("list"), fn.fresh("i")
    fn.emit(f"const {c_type(ct)} {holder} = {container};")
    if ct == "Array":
        item, element = f"{holder}[{index}]", "Variant"
    else:
        item, element = f"int64_t({holder}[{index}])", "int"
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


def _return(fn: Function, node: dict) -> None:
    gd = gd_type(fn.node["return"])
    if node["value"] is not None:
        fn.emit(f"return {typed(fn, node['value'], gd)};")
    else:
        fn.emit("return;" if gd == "void" else f"return {c_type(gd)}();")


def _pass(fn: Function, node: dict) -> None:
    pass


_STATEMENTS: dict[str, Callable[[Function, dict], None]] = {
    "assignment": assignment,
    "variable": _variable,
    "if": _if,
    "while": _while,
    "for": _for,
    "return": _return,
    "pass": _pass,
}
