"""
The types the C++ generator works with, and how values change between them.

A GDScript type becomes a builtin name (`int`, `String`, `Vector2i`, ...), `void`,
`Variant`, or for objects `C:<script class>` and `O:<native class>`, and for type names
used as values `M:<script class>` and `N:<native class>`. Objects are `Variant`s in C++.
"""

import json
import re
from collections.abc import Callable


class Unsupported(Exception):
    """A construct the prototype does not compile."""


# GDScript builtin type -> C++ type, VariantInternal getter, Variant::Type.
BUILTINS = {
    "int": ("int64_t", "get_int", "INT"),
    "float": ("double", "get_float", "FLOAT"),
    "bool": ("bool", "get_bool", "BOOL"),
    "String": ("String", "get_string", "STRING"),
    "StringName": ("StringName", "get_string_name", "STRING_NAME"),
    "NodePath": ("NodePath", "get_node_path", "NODE_PATH"),
    "Vector2": ("Vector2", "get_vector2", "VECTOR2"),
    "Vector2i": ("Vector2i", "get_vector2i", "VECTOR2I"),
    "Vector3": ("Vector3", "get_vector3", "VECTOR3"),
    "Vector3i": ("Vector3i", "get_vector3i", "VECTOR3I"),
    "Vector4": ("Vector4", "get_vector4", "VECTOR4"),
    "Vector4i": ("Vector4i", "get_vector4i", "VECTOR4I"),
    "Rect2": ("Rect2", "get_rect2", "RECT2"),
    "Rect2i": ("Rect2i", "get_rect2i", "RECT2I"),
    "Transform2D": ("Transform2D", "get_transform2d", "TRANSFORM2D"),
    "Transform3D": ("Transform3D", "get_transform", "TRANSFORM3D"),
    "Basis": ("Basis", "get_basis", "BASIS"),
    "Quaternion": ("Quaternion", "get_quaternion", "QUATERNION"),
    "Plane": ("Plane", "get_plane", "PLANE"),
    "AABB": ("::AABB", "get_aabb", "AABB"),
    "Projection": ("Projection", "get_projection", "PROJECTION"),
    "Color": ("Color", "get_color", "COLOR"),
    "RID": ("::RID", "get_rid", "RID"),
    "Callable": ("Callable", "get_callable", "CALLABLE"),
    "Signal": ("Signal", "get_signal", "SIGNAL"),
    "Array": ("Array", "get_array", "ARRAY"),
    "Dictionary": ("Dictionary", "get_dictionary", "DICTIONARY"),
    "PackedByteArray": ("PackedByteArray", "get_byte_array", "PACKED_BYTE_ARRAY"),
    "PackedInt32Array": ("PackedInt32Array", "get_int32_array", "PACKED_INT32_ARRAY"),
    "PackedInt64Array": ("PackedInt64Array", "get_int64_array", "PACKED_INT64_ARRAY"),
    "PackedFloat32Array": (
        "PackedFloat32Array",
        "get_float32_array",
        "PACKED_FLOAT32_ARRAY",
    ),
    "PackedFloat64Array": (
        "PackedFloat64Array",
        "get_float64_array",
        "PACKED_FLOAT64_ARRAY",
    ),
    "PackedStringArray": ("PackedStringArray", "get_string_array", "PACKED_STRING_ARRAY"),
    "PackedVector2Array": (
        "PackedVector2Array",
        "get_vector2_array",
        "PACKED_VECTOR2_ARRAY",
    ),
    "PackedVector3Array": (
        "PackedVector3Array",
        "get_vector3_array",
        "PACKED_VECTOR3_ARRAY",
    ),
    "PackedColorArray": ("PackedColorArray", "get_color_array", "PACKED_COLOR_ARRAY"),
    "PackedVector4Array": (
        "PackedVector4Array",
        "get_vector4_array",
        "PACKED_VECTOR4_ARRAY",
    ),
}
NUMBERS = ("int", "float")
_SCALARS = {"int", "float", "bool"}


def _builtin_kind(t: dict) -> str:
    name = t.get("builtin")
    if name == "Nil":
        return "void"
    return name if name in BUILTINS else "Variant"


def _script_kind(t: dict) -> str:
    name = t.get("class") or t.get("script")
    if not name:
        return "Variant"
    return ("M:" if t.get("meta") else "C:") + name


def _native_kind(t: dict) -> str:
    return ("N:" if t.get("meta") else "O:") + t["native"]


_KINDS: dict[str, Callable[[dict], str]] = {
    "builtin": _builtin_kind,
    "class": _script_kind,
    "script": _script_kind,
    "native": _native_kind,
}


def gd_type(t: dict | None) -> str:
    """The generator's type for a dumped data type; Variant unless statically typed."""
    if not t or not t.get("hard"):
        return "Variant"
    kind = _KINDS.get(t.get("kind", ""))
    return kind(t) if kind else "Variant"


def c_type(gd: str) -> str:
    if gd == "void":
        return "void"
    if gd == "Variant" or ":" in gd:
        return "Variant"
    return BUILTINS[gd][0]


def _unchanged(source: str, target: str) -> bool:
    # Objects are Variants; the analyzer checked the class.
    return (
        source == target
        or target == "void"
        or c_type(source) == c_type(target) == "Variant"
    )


def convert(code: str, source: str, target: str) -> str:
    """code of type source as an expression of type target."""
    if _unchanged(source, target):
        return code
    if target == "Variant":
        return f"Variant({code})"
    if source == "Variant":
        return f"(({c_type(target)})({code}))"
    if {source, target} <= _SCALARS:
        return f"{c_type(target)}({code})"
    if (source, target) == ("String", "StringName"):
        return f"StringName({code})"
    raise Unsupported(f"conversion {source} -> {target}")


def truth(code: str, gd: str) -> str:
    """code as a C++ condition."""
    if gd == "bool":
        return code
    if gd == "Variant":
        return f"({code}).booleanize()"
    return f"Variant({code}).booleanize()"


def _unquote(text: str) -> str:
    """The content of a string as `var_to_str()` writes it: quoted, with only `\\` and
    `"` escaped and line breaks kept."""
    return re.sub(r"\\(.)", r"\1", text[1:-1], flags=re.DOTALL)


def _string_literal(text: str) -> tuple[str, str]:
    # Built once and never freed, like the VM's constants.
    quoted = json.dumps(_unquote(text), ensure_ascii=False)
    built = (
        f"static const String *value = new String(String::utf8({quoted})); return *value;"
    )
    return f"([]() -> const String & {{ {built} }})()", "String"


def _parsed_literal(text: str) -> tuple[str, str]:
    # Parsed once and never freed: a static Variant would be destroyed after the engine.
    escaped = json.dumps(text)
    parsed = f"static const Variant *value = new Variant(GDScriptNative::constant({escaped})); return *value;"
    return f"([]() -> const Variant & {{ {parsed} }})()", "Variant"


_LITERALS: dict[str, Callable[[str], tuple[str, str]]] = {
    "int": lambda text: (f"int64_t({text})", "int"),
    "float": lambda text: (f"double({text})", "float"),
    "bool": lambda text: (text, "bool"),
    "String": _string_literal,
    "Nil": lambda text: ("Variant()", "Variant"),
}


def literal(value: dict) -> tuple[str, str]:
    """A constant as C++, with its type."""
    kind, text = value["type"], value["text"]
    if kind in _LITERALS:
        return _LITERALS[kind](text)
    if kind in BUILTINS or kind.startswith("Packed"):
        return _parsed_literal(text)
    raise Unsupported(f"constant of type {kind}")
