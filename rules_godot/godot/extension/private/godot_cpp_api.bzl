"""
The API selection of godot_cpp_bindings: which classes upstream's build profile keeps and
which files its generator writes for them.
"""

visibility(["//godot/extension/private/..."])

def _starts_word(name, i):
    # A capital starts a word after a lowercase letter or a digit. In an acronym, the last
    # capital starts the next word, as the R of HTTPRequest does.
    if not i or not name[i].isupper():
        return False
    previous = name[i - 1]
    if previous.islower() or previous.isdigit():
        return True
    return i + 1 < len(name) and name[i + 1].islower()

def _snake(name):
    result = ""
    for i in range(len(name)):
        if _starts_word(name, i):
            result += "_"
        result += name[i]
    return result.replace("2_D", "2D").replace("3_D", "3D").lower()

_BUILTIN_IMPLEMENTED = [
    "Nil",
    "void",
    "bool",
    "real_t",
    "float",
    "double",
    "int",
    "int8_t",
    "uint8_t",
    "int16_t",
    "uint16_t",
    "int32_t",
    "int64_t",
    "uint32_t",
    "uint64_t",
    "AABB",
    "Basis",
    "Color",
    "Plane",
    "Projection",
    "Quaternion",
    "Rect2",
    "Rect2i",
    "Transform2D",
    "Transform3D",
    "Vector2",
    "Vector2i",
    "Vector3",
    "Vector3i",
    "Vector4",
    "Vector4i",
    "ObjectID",
]

# The files the generator writes for every API selection.
_FIXED_HEADERS = [
    "core/gdextension_interface_loader.hpp",
    "core/ext_wrappers.gen.inc",
    "core/gdvirtual.gen.inc",
    "variant/builtin_types.hpp",
    "variant/builtin_binds.hpp",
    "variant/utility_functions.hpp",
    "variant/variant_size.hpp",
    "variant/builtin_vararg_methods.hpp",
    "classes/global_constants.hpp",
    "classes/global_constants_binds.hpp",
    "core/version.hpp",
]
_FIXED_SOURCES = ["gdextension_interface_loader.cpp", "variant/utility_functions.cpp"]

def binding_outputs(api, enabled):
    """
    The files the generator writes for an API selection, relative to the repository.

    Args:
        api: The decoded extension API JSON.
        enabled: The classes kept, as included_classes returns them; empty for every class.

    Returns:
        The interface header, the bindings' headers and their sources.
    """
    builtins = [
        _snake(builtin["name"])
        for builtin in api["builtin_classes"]
        if builtin["name"] not in _BUILTIN_IMPLEMENTED
    ]

    # godot-cpp binds ClassDB as ClassDBSingleton.
    classes = [
        _snake("ClassDBSingleton" if cls["name"] == "ClassDB" else cls["name"])
        for cls in api["classes"]
        if not enabled or cls["name"] in enabled
    ]
    natives = [_snake(native["name"]) for native in api["native_structures"] if native["name"] != "ObjectID"]
    headers = (
        _FIXED_HEADERS +
        ["variant/" + name + ".hpp" for name in builtins] +
        ["classes/" + name + ".hpp" for name in classes + natives]
    )
    sources = (
        _FIXED_SOURCES +
        ["variant/" + name + ".cpp" for name in builtins] +
        ["classes/" + name + ".cpp" for name in classes]
    )
    return (
        ["gen/include/gdextension_interface.h"] +
        ["gen/include/godot_cpp/" + h for h in headers] +
        ["gen/src/" + s for s in sources]
    )

# The classes upstream's build profile always keeps.
_MANDATORY_CLASSES = [
    "WorkerThreadPool",
    "ClassDB",
    "ClassDBSingleton",
    "FileAccess",
    "Image",
    "XMLParser",
    "OS",
]

def _lineage(name, parents):
    """The class and its ancestors."""
    lineage = []
    current = name

    # Starlark has no while loop; no chain of ancestors is longer than the API's classes.
    for _ in range(len(parents) + 1):
        if not current:
            break
        lineage.append(current)
        current = parents.get(current, "")
    return lineage

def included_classes(api, selected, _fail):
    """
    The classes a selection keeps: the selected ones, the mandatory ones and their ancestors.

    Args:
        api: The decoded extension API JSON.
        selected: The enabled_classes of godot_cpp_bindings; empty for every class.
        _fail: Called with the message of an unknown class.

    Returns:
        The class names, empty for every class, or None after an error.
    """
    if not selected:
        return []
    parents = {cls["name"]: cls.get("inherits", "") for cls in api["classes"]}
    unknown = [name for name in selected if name not in parents]
    if unknown:
        _fail("unknown enabled godot-cpp class: " + unknown[0])
        return None

    # As upstream's build profile does, keep the mandatory classes and every ancestor.
    included = {
        ancestor: True
        for name in selected + _MANDATORY_CLASSES
        for ancestor in _lineage(name, parents)
    }
    return included.keys()
