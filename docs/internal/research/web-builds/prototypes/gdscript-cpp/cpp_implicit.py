"""
The functions Godot's compiler writes for a class itself: `@implicit_new`, which gives
every typed member its type's default value and then runs the members' initializers, and
`@implicit_ready`, which runs the initializers of `@onready` members. They are built here
as syntax trees from the member declarations, so the generator compiles them like any
other function, and the VM runs none of a class's code.
"""

from cpp_expressions import element_type
from cpp_types import BUILTINS, gd_type

_VOID = {"kind": "builtin", "hard": True, "builtin": "Nil"}


def _function(name: str, statements: list[dict]) -> dict:
    return {
        "node": "function",
        "name": name,
        "static": False,
        "coroutine": False,
        "vararg": False,
        "return": _VOID,
        "parameters": [],
        "body": {"node": "suite", "statements": statements},
    }


def _default(index: int, t: dict) -> dict | None:
    """The statement giving a typed member its type's default value, as the compiler does
    before any initializer runs; objects stay null."""
    gd = gd_type(t)
    if gd == "Array" and t.get("elements"):
        code = f"GDScriptNative::typed_array({element_type(t['elements'][0])}, {{}})"
    elif gd in BUILTINS:
        code = f"Variant({BUILTINS[gd][0]}())"
    else:
        return None
    return {"node": "raw", "code": f"p_members[{index}] = {code};"}


def _initialize(variable: dict) -> dict:
    member = {
        "node": "identifier",
        "name": variable["name"],
        "source": "member_variable",
        "type": variable["type"],
    }
    return {
        "node": "assignment",
        "operator": "",
        "assignee": member,
        "value": variable["initializer"],
    }


def implicit_functions(variables: list[dict], indices: dict[str, int]) -> list[dict]:
    """`@implicit_new` and, with `@onready` members, `@implicit_ready`; none for a class
    with static members, whose initializer stays bytecode."""
    members = [v for v in variables if not v["static"]]
    if len(members) != len(variables):
        return []
    defaults = [_default(indices[v["name"]], v["type"]) for v in members]
    created = [*filter(None, defaults)]
    created += [_initialize(v) for v in members if v["initializer"] and not v["onready"]]
    functions = [_function("@implicit_new", created)]
    if any(v["onready"] for v in members):
        ready = [_initialize(v) for v in members if v["initializer"] and v["onready"]]
        functions.append(_function("@implicit_ready", ready))
    return functions
