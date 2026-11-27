"""
The implementation of godot_cpp_bindings in godot/extension:repositories.bzl.

Errors go through `_fail`, so a Starlark unit test with a mocked repository_ctx collects
them; the implementation returns after an error.
"""

load("//godot/private:patches.bzl", "apply_repository_patches")
load("//godot/private:repository_templates.bzl", "starlark_list")
load("//godot/private:supply_chain.bzl", "source_purl", "write_package_metadata")

visibility(["//godot/extension/..."])

# godot-cpp 10.0.0-stable, with the Godot 4.7 API and generated ABI loader.
GODOT_CPP_COMMIT = "507ed9d840c01a3c5b2a39af8bb4000bfac30bf5"
GODOT_CPP_SHA256 = "30da4ac295997061a6af81ae531510efd4e6a86e506eb4466edc0898ef3fe048"

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

def _outputs(api, enabled):
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

def _included_classes(api, selected, _fail):
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

def godot_cpp_bindings_impl(ctx, *, _fail = fail):
    """
    Fetch godot-cpp and generate the BUILD file of its bindings for one API selection.

    Args:
        ctx: Repository rule context of godot_cpp_bindings.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible when the archive is checksum-pinned.
    """
    ctx.download_and_extract(
        url = ctx.attr.urls,
        sha256 = ctx.attr.sha256,
        stripPrefix = ctx.attr.strip_prefix,
        type = "tar.gz",
    )
    if not apply_repository_patches(ctx, _fail = _fail):
        return None
    api = json.decode(ctx.read(ctx.attr.api_path))
    if api["header"]["version_major"] != 4 or api["header"]["version_minor"] < 7:
        _fail("godot_cpp_bindings requires a Godot 4.7 or newer API within Godot 4")
        return None
    enabled = _included_classes(api, ctx.attr.enabled_classes, _fail)
    if enabled == None:
        return None
    profile = None
    profile_generator = None
    if enabled:
        # Retain classes referenced by handwritten C++ sources in both the
        # output manifest and the upstream profile generator's input.
        ctx.file(
            "rules_godot_profile.json",
            json.encode({"enabled_classes": ctx.attr.enabled_classes + ["OS"]}),
        )
        profile = "rules_godot_profile.json"
        profile_generator = "build_profile.py"
    source_def = str(ctx.attr._defs)
    defines = ["GDEXTENSION", "THREADS_ENABLED"] + (
        ["REAL_T_IS_DOUBLE"] if ctx.attr.precision == "double" else []
    ) + (
        ["DEBUG_ENABLED", "HOT_RELOAD_ENABLED"] if ctx.attr.debug_features else []
    )
    ctx.template("BUILD.bazel", ctx.attr._build_template, substitutions = {
        "{BINDINGS_BZL}": repr(source_def),
        "{CC_LIBRARY_BZL}": repr(str(ctx.attr._cc_library)),
        "{API}": repr(ctx.attr.api_path),
        "{BITS}": repr(ctx.attr.bits),
        "{PRECISION}": repr(ctx.attr.precision),
        "{OUTS}": starlark_list(sorted(_outputs(api, enabled)), indent = "    "),
        "{PROFILE}": repr(profile),
        "{PROFILE_GENERATOR}": repr(profile_generator),
        "{DEFINES}": starlark_list(defines, indent = "    "),
        "{WINDOWS}": repr(str(ctx.attr._windows_constraint)),
    })
    write_package_metadata(
        ctx,
        source_purl("godot-cpp", sha256 = ctx.attr.sha256),
        "LICENSE.md",
    )

    # A checksum-pinned archive and its patches determine the contents, so Bazel's repo
    # contents cache, local or remote, may reuse them.
    return ctx.repo_metadata(reproducible = bool(ctx.attr.sha256))
