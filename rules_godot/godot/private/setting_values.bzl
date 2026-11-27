"""Setting values as tools/project/config.py reads them: their kinds, feature overrides and the files they name."""

visibility("//godot/private/...")

# A key outside Godot's sections, such as an add-on's own key: content-bound, with the
# shape of what its declaration names. setting_values.bzl and tools/project/config.py decide the
# kinds and named paths alike; tests/setting_values.bzl holds the cases both meet.
_UNKNOWN_KIND = {"binding": "content", "shape": None}

def names_directories(kind):
    """
    Whether a setting of kind may name a directory, as tools/project/config.py decides (FR-032).

    A setting Godot hints as a file names files, and so does an autoload; any other, an
    add-on's own key included, may name a directory, which a file below it provides.
    """
    return kind.get("hint") != "file" and kind["shape"] != "autoload"

def setting_kind(kinds, key):
    """
    Return the kind of a setting or of a feature override's base setting, as tools/project/config.py does.

    Args:
        kinds: The setting kinds and sections of the engine version, from configuration_kinds.
        key: A section/property key, such as gui/theme/custom.mobile.

    Returns:
        The table's row, a content-bound kind of no shape for a key outside Godot's
        sections, or None for another setting of Godot.
    """
    base = key.partition(".")[0]
    section = base.partition("/")[0]
    row = kinds.kinds.get(base) or kinds.kinds.get(section + "/*")
    if row:
        return row
    if "/" in base and section not in kinds.sections:
        return _UNKNOWN_KIND
    return None

def override_applies(key, features):
    """
    Whether a setting key applies under features, as tools/project/config.py decides.

    Godot applies a feature override such as gui/theme/custom.mobile when one of its tags
    is a feature the game has; a key without a tag always applies.

    Args:
        key: A section/property key.
        features: The feature tags an operation can have, or None for any.

    Returns:
        True unless the key has tags and features holds none of them.
    """
    tags = key.split(".")[1:]
    return features == None or not tags or any([tag in features for tag in tags])

_PACKED_STRING_ARRAY = "PackedStringArray("
_CLOSING = {"(": ")", "[": "]", "{": "}"}

def _quoted(char, escape):
    """Whether a string literal goes on after char, and whether char escapes the next one."""
    if escape:
        return True, False
    return char != '"', char == "\\"

def _godot_value(literal):
    """Decode a Godot literal that JSON can read once packed string arrays are lists, or None."""
    text = []
    closing = []
    quote = False
    escape = False
    skip = 0
    for index in range(len(literal)):
        if skip:
            skip -= 1
            continue
        char = literal[index]
        if quote:
            quote, escape = _quoted(char, escape)
        elif char == '"':
            quote = True
        elif literal.startswith(_PACKED_STRING_ARRAY, index):
            text.append("[")
            closing.append("]")
            skip = len(_PACKED_STRING_ARRAY) - 1
            continue
        elif char in _CLOSING:
            closing.append(_CLOSING[char])
        elif char in ")]}" and closing:
            char = closing.pop()
        text.append(char)
    return json.decode("".join(text), default = None)

def _strings(value):
    if type(value) == "string":
        return [value]
    if type(value) == "list":
        return [item for item in value if type(item) == "string"]
    return []

def _remapped(value):
    """The path of a translation remap such as res://hello_de.ogg:de, without its locale."""
    path, separator, locale = value.rpartition(":")
    return path if separator and "/" not in locale else value

def _path_map_paths(value):
    """A translation remap's sources and remapped files without their locale."""
    if type(value) != "dict":
        return []
    return [
        path
        for source, remaps in value.items()
        for path in [source] + [_remapped(remap) for remap in _strings(remaps)]
    ]

def named_paths(shape, literal):
    """
    Return the strings a file-referencing setting's Godot literal names, as tools/project/config.py does.

    Args:
        shape: The setting's shape in the setting-kind table, or None for a declared key
            unknown to the table, which names a string or an array of strings.
        literal: The setting's Godot literal, such as "res://a.tres" or
            PackedStringArray("res://a.tres").

    Returns:
        The named strings: an autoload's without its singleton `*`, a translation remap's
        sources and remapped files without their locale, a shader global's sampler file,
        and for the other shapes the string or array of strings; empty for any other value.
    """
    value = _godot_value(literal.strip())
    if shape == "autoload":
        return [path.removeprefix("*") for path in _strings(value)]
    if shape == "path_map":
        return _path_map_paths(value)
    if shape == "shader_global":
        return _strings(value.get("value")) if type(value) == "dict" else []
    return _strings(value)
