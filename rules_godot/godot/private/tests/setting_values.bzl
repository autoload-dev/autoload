"""
What a setting's key and Godot literal name, and whether a feature override applies: the
cases setting_values.bzl, during analysis, and tools/project/config.py, in actions, must decide alike.
project_config_test.py checks both.
"""

load("//godot/private:setting_values.bzl", "named_paths", "override_applies", "setting_kind")
load("//godot/private/engine:setting_kinds.bzl", "engine_sections", "setting_kinds")

visibility("private")

# Key, literal and what they name: the kind's binding and the named strings, or None for a
# setting of Godot that names no file.
_CASES = [
    ("gui/theme/custom", '"res://a.tres"', ["content", ["res://a.tres"]]),
    ("gui/theme/custom.mobile", '"res://m.tres"', ["content", ["res://m.tres"]]),
    ("gui/theme/custom", "Vector2(1, 2)", ["content", []]),
    ("application/config/icon", '"res://icon.svg"', ["context", ["res://icon.svg"]]),
    ("autoload/App", '"*res://a.gd"', ["content", ["res://a.gd"]]),
    (
        "internationalization/locale/translations",
        'PackedStringArray("res://a", "res://b")',
        ["content", ["res://a", "res://b"]],
    ),
    (
        "internationalization/locale/translation_remaps",
        '{"res://a.ogg": PackedStringArray("res://a_de.ogg:de", "res://a(1).ogg:fr")}',
        ["content", ["res://a.ogg", "res://a_de.ogg", "res://a(1).ogg"]],
    ),
    ("shader_globals/noise", '{"type": "sampler2D", "value": "res://n.png"}', ["content", ["res://n.png"]]),
    ("shader_globals/scale", '{"type": "float", "value": 1.0}', ["content", []]),
    ("addon_own/data", '"res://own.tres"', ["content", ["res://own.tres"]]),
    ("addon_own/list", 'PackedStringArray("res://x", "uid://y")', ["content", ["res://x", "uid://y"]]),
    ("addon_own/flag", "true", ["content", []]),
    ("editor/script/templates_search_path", '"res://templates"', [None, ["res://templates"]]),
    ("application/config/name", '"Demo"', None),
    ("config_version", "5", None),
]

# Key, the features an operation can have (None for any) and whether the key applies there,
# which decides whether a program entry needs the files it names.
_OVERRIDE_CASES = [
    ("gui/theme/custom", ["mobile"], True),
    ("gui/theme/custom.mobile", ["android", "mobile"], True),
    ("gui/theme/custom.debug_tools", ["android", "mobile"], False),
    ("gui/theme/custom.debug_tools", None, True),
    ("gui/theme/custom.debug_tools", [], False),
    ("application/run/main_scene.gdunit_host.mobile", ["mobile"], True),
]

def setting_value_cases():
    """
    Return the cases with setting_values.bzl's decision for each, under Godot 4.7's setting kinds.

    Returns:
        JSON of a list of objects with key, literal, expected and starlark.
    """
    kinds = struct(kinds = setting_kinds("4.7.2"), sections = engine_sections("4.7.2"))
    cases = []
    for key, literal, expected in _CASES:
        kind = setting_kind(kinds, key)
        cases.append({
            "expected": expected,
            "key": key,
            "literal": literal,
            "starlark": [kind["binding"], named_paths(kind["shape"], literal)] if kind else None,
        })
    return json.encode(cases)

def override_cases():
    """
    Return the override cases with setting_values.bzl's decision for each.

    Returns:
        JSON of a list of objects with key, features, expected and starlark.
    """
    return json.encode([
        {
            "expected": expected,
            "features": features,
            "key": key,
            "starlark": override_applies(key, features),
        }
        for key, features, expected in _OVERRIDE_CASES
    ])
