"""
Compose explicit Godot settings without evaluating arbitrary expressions.

The command line of //tools:project_config is project_config_command.py.

The statements it reads are project_statements.py's.

Sections: Literals, Named files, Overrides, Plugins and autoloads,
Composition, Write back.
"""

import dataclasses
import json
import re
from collections.abc import Callable, Collection, Iterable

from tools.project_statements import (
    CLOSING,
    SECTION,
    TextScan,
    setting_key,
    setting_section,
    statement_groups,
    statement_value,
)

# ==== Literals ================================================================


_CONSTRUCTORS = {
    "Color",
    "Vector2",
    "Vector2i",
    "Vector3",
    "Vector3i",
    "Vector4",
    "Vector4i",
    "Rect2",
    "Rect2i",
    "Transform2D",
    "Plane",
    "Quaternion",
    "AABB",
    "Basis",
    "Transform3D",
    "Projection",
    "StringName",
    "NodePath",
    "RID",
    "PackedByteArray",
    "PackedInt32Array",
    "PackedInt64Array",
    "PackedFloat32Array",
    "PackedFloat64Array",
    "PackedStringArray",
    "PackedVector2Array",
    "PackedVector3Array",
    "PackedVector4Array",
    "PackedColorArray",
}

_TOKEN = re.compile(
    r'\s*(?:(-inf\b|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)|([A-Za-z_][A-Za-z_0-9]*)|("(?:[^"\\\r\n]|\\.)*")|([\[\]{}(),:&^]))'
)

_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")

_KEYWORDS = {"true", "false", "null", "inf", "-inf", "inf_neg", "nan"}


def _tokens(value: str) -> list[str]:
    """Split a Godot literal into tokens; a character no token starts with fails."""
    tokens = []
    offset = 0
    while offset < len(value):
        match = _TOKEN.match(value, offset)
        if not match:
            raise ValueError(f"Unsupported Godot literal syntax: {value!r}")
        tokens.append(next(group for group in match.groups() if group is not None))
        offset = match.end()
    return tokens


def _is_scalar(token: str) -> bool:
    """Whether a token is a whole value: a string, a number or a keyword."""
    return token.startswith('"') or bool(_NUMBER.fullmatch(token)) or token in _KEYWORDS


class _Literal:
    """A recursive-descent check of one Godot literal's tokens."""

    def __init__(self, value: str) -> None:
        self.value = value
        self.tokens = _tokens(value)
        self.position = 0

    def parse_value(self) -> None:
        """Consume one value: a scalar, a name, an array, a dictionary or a constructor."""
        token = self._consume()
        if _is_scalar(token):
            return
        if token in {"&", "^"}:
            self._string_operand()
        elif token == "[":
            self._sequence("]", self.parse_value)
        elif token == "{":
            self._sequence("}", self._entry)
        elif token in _CONSTRUCTORS:
            self._consume("(")
            self._sequence(")", self.parse_value)
        else:
            raise ValueError(f"Unsupported Godot literal token: {token}")

    def done(self) -> bool:
        """Whether every token was consumed."""
        return self.position == len(self.tokens)

    def _consume(self, expected: str | None = None) -> str:
        token = self.tokens[self.position] if not self.done() else None
        if token is None or expected not in (None, token):
            raise ValueError(
                f"Expected {expected or 'a value'} in Godot literal: {self.value!r}"
            )
        self.position += 1
        return token

    def _closes(self, closing: str) -> bool:
        """Consume closing if it comes next; whether it did."""
        if self.done() or self.tokens[self.position] != closing:
            return False
        self.position += 1
        return True

    def _sequence(self, closing: str, item: Callable[[], None]) -> None:
        """Items separated by commas, a trailing one allowed, up to closing."""
        while not self._closes(closing):
            item()
            if self._closes(closing):
                return
            self._consume(",")

    def _entry(self) -> None:
        self.parse_value()
        self._consume(":")
        self.parse_value()

    def _string_operand(self) -> None:
        if not self._consume().startswith('"'):
            raise ValueError("Godot StringName and NodePath literals require a string")


def validate_literal(value: str) -> str:
    """Parse basic Godot scalar/container/constructor literals without evaluation."""
    value = value.strip()
    literal = _Literal(value)
    literal.parse_value()
    if not literal.done():
        raise ValueError(f"Unexpected trailing tokens in Godot literal: {value!r}")
    return value


_PACKED_STRING_ARRAY = "PackedStringArray("


def _matched_bracket(char: str, closing: list[str]) -> str:
    """Track an opening bracket, or close the innermost one with its own kind."""
    if char in "([{":
        closing.append(CLOSING[char])
    elif char in ")]}" and closing:
        return closing.pop()
    return char


def _godot_value(literal: str) -> object:
    """Decode a Godot literal that JSON can read once packed string arrays are lists."""
    text = []
    closing = []
    scan = TextScan()
    index = 0
    while index < len(literal):
        char = literal[index]
        if scan.in_string(char):
            text.append(char)
        elif literal.startswith(_PACKED_STRING_ARRAY, index):
            text.append("[")
            closing.append("]")
            index += len(_PACKED_STRING_ARRAY)
            continue
        else:
            text.append(_matched_bracket(char, closing))
        index += 1
    try:
        return json.loads("".join(text))
    except ValueError:
        return None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


# ==== Named files =============================================================


# A key outside Godot's sections, such as an add-on's own key: program-level, so no
# import carries it, and content-bound. Its shape is what its declaration names.
UNKNOWN_KIND = {
    "binding": "content",
    "hint": None,
    "purposes": ["export", "runtime", "editor"],
    "shape": None,
}


def _outside_godot(section: str | None, sections: Iterable[str] | None) -> bool:
    """Whether a setting's section is none of Godot's; a root key is always Godot's."""
    if sections is None or section is None:
        return False
    return section not in sections


def setting_kind(
    setting: str, kinds: dict[str, dict], sections: Iterable[str] | None
) -> dict | None:
    """
    Return the kind of a setting or of a feature override's base setting, as setting_values.bzl does.

    Args:
        setting: A section/property key, such as gui/theme/custom.mobile.
        kinds: The setting-kind table of the engine version.
        sections: The sections of Godot's own settings; None knows every key.

    Returns:
        The table's row, UNKNOWN_KIND for a key outside Godot's sections, or None for
        a setting of Godot that names no file.
    """
    base = setting.partition(".")[0]
    section = setting_section(base)
    row = kinds.get(base) or kinds.get(f"{section}/*")
    if row:
        return row
    return UNKNOWN_KIND if _outside_godot(section, sections) else None


def _remapped(value: str) -> str:
    """The path of a translation remap such as res://hello_de.ogg:de, without its locale."""
    path, separator, locale = value.rpartition(":")
    return path if separator and "/" not in locale else value


def _autoload_paths(value: object) -> list[str]:
    return [path.removeprefix("*") for path in _strings(value)]


def _path_map_paths(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [
        path
        for source, remaps in value.items()
        for path in [source] + [_remapped(remap) for remap in _strings(remaps)]
    ]


def _shader_global_paths(value: object) -> list[str]:
    return _strings(value.get("value")) if isinstance(value, dict) else []


# The strings each shape names in a setting's decoded value; any other names its strings.
_SHAPE_PATHS: dict[str | None, Callable[[object], list[str]]] = {
    "autoload": _autoload_paths,
    "path_map": _path_map_paths,
    "shader_global": _shader_global_paths,
}


def named_paths(shape: str | None, literal: str) -> list[str]:
    """
    Return the strings a file-referencing setting's Godot literal names, as setting_values.bzl does.

    Args:
        shape: The setting's shape in the setting-kind table, or None for a declared
            key unknown to the table, which names a string or an array of strings.
        literal: The setting's Godot literal.

    Returns:
        The named strings: an autoload's without its singleton `*`, a translation
        remap's sources and remapped files without their locale, a shader global's
        sampler file, and for the other shapes the string or array of strings; empty
        for any other value.
    """
    return _SHAPE_PATHS.get(shape, _strings)(_godot_value(literal))


def names_directories(kind: dict) -> bool:
    """
    Whether a setting of kind may name a directory, as setting_values.bzl decides (FR-032).

    A setting Godot hints as a file names files, and so does an autoload; any other, an
    add-on's own key included, may name a directory, which a file below it provides.
    """
    return kind.get("hint") != "file" and kind["shape"] != "autoload"


def _names_game_files(kind: dict, literal: str) -> bool:
    """
    Whether a setting of kind names a file of the game, which a context-only configuration drops.

    A content-bound setting of Godot always counts; a key unknown to Godot counts when
    its literal names a res:// path.
    """
    if kind["binding"] != "content":
        return False
    return kind is not UNKNOWN_KIND or any(
        path.startswith("res://") for path in named_paths(None, literal)
    )


def _declared(path: str, members: set[str], directory: bool) -> bool:
    """Whether members hold the file path, or with directory a file below it."""
    path = path.rstrip("/")
    if path in members:
        return True
    return directory and any(member.startswith(path + "/") for member in members)


def left_out(
    base: str,
    kinds: dict[str, dict],
    members: Iterable[str],
) -> list[tuple[str, str]]:
    """
    Return the content-bound settings of the authored file that name a file members lack.

    A uid:// reference, or any value other than a res:// path, stays: only its
    declaration would say which file it names. Feature overrides count whatever their
    tags: a view leaves out each one whose file it lacks.

    Args:
        base: The authored project.godot text.
        kinds: The setting-kind table of the engine version.
        members: The view's member resource paths.

    Returns:
        (setting, path) pairs, the first missing path of each setting, in file order.
    """
    present = set(members)
    result = []
    for text, section, key in statement_groups(base):
        if key is None:
            continue
        setting = setting_key(section, key)
        kind = setting_kind(setting, kinds, None)
        if kind is None or kind["binding"] != "content":
            continue
        directory = names_directories(kind)
        missing = [
            path
            for path in named_paths(kind["shape"], statement_value(text).strip())
            if path.startswith("res://")
            and not _declared(path.removeprefix("res://"), present, directory)
        ]
        if missing:
            result.append((setting, missing[0]))
    return result


# ==== Overrides ===============================================================


def feature_tags(key: str) -> list[str]:
    """Return the feature tags of an override key such as ``method.mobile``."""
    return key.split(".")[1:]


def override_applies(key: str, features: Collection[str] | None) -> bool:
    """
    Whether a setting key applies under features, as setting_values.bzl decides.

    Godot applies a feature override such as ``custom.mobile`` when one of its tags is a
    feature the game has; a key without a tag always applies. None for features counts
    every override.
    """
    tags = feature_tags(key)
    return features is None or not tags or any(tag in features for tag in tags)


def override_tags(base: str, settings: Iterable[str]) -> list[str]:
    """Return every feature tag that a base or contributed setting overrides with."""
    keys = [key for _, _, key in statement_groups(base) if key is not None]
    keys += [setting.split("/", 1)[1] for setting in settings]
    return sorted({tag for key in keys for tag in feature_tags(key)})


def _overrides_of(base: str, settings: Collection[str]) -> list[str]:
    """The feature overrides of settings that base authors, such as ``key.mobile``."""
    return [
        setting
        for _, section, key in statement_groups(base)
        if key is not None
        and feature_tags(key)
        and (setting := setting_key(section, key)).partition(".")[0] in settings
    ]


def shadowed(base: str, flag_keys: dict[str, str]) -> list[str]:
    """
    Describe each feature override in base of a setting a project's settings_from_flags
    set, which would hide the flag's value where its tag applies.

    Args:
        base: Authored project.godot text.
        flag_keys: The settings settings_from_flags set, to their flags' labels.
    """
    flags = {key.split(".")[0]: flag for key, flag in flag_keys.items()}
    found = []
    for _, section, key in statement_groups(base):
        if key is None:
            continue
        setting = setting_key(section, key)
        # A flag's own override sets the flag's value, and a plain setting hides nothing.
        if setting in flag_keys or not feature_tags(setting):
            continue
        flag = flags.get(setting.split(".")[0])
        if flag:
            found.append(
                f"The authored project.godot overrides {setting}, which hides the "
                f"value {flag} gives through settings_from_flags"
            )
    return found


# ==== Plugins and autoloads ===================================================


def authored_autoloads(base: str) -> dict[str, str]:
    """
    Return the autoloads of an authored project.godot, name to value as Godot writes it.

    A feature override of an autoload, and a value that is no string, stay out.

    Args:
        base: The authored project.godot text.

    Returns:
        The values by name, such as "*res://a.gd" or "*uid://...", in file order.
    """
    autoloads = {}
    for text, section, key in statement_groups(base):
        if section != "autoload" or key is None:
            continue
        value = _godot_value(statement_value(text).strip())
        if isinstance(value, str) and not feature_tags(key):
            autoloads[key] = value
    return autoloads


def enabled_plugins(text: str) -> list[str]:
    """Return the plugin.cfg paths project.godot text enables."""
    enabled: list[str] = []
    for group, section, key in statement_groups(text):
        if section == "editor_plugins" and key == "enabled":
            value = statement_value(group).strip()
            paths = (
                _godot_value(value) if value.startswith(_PACKED_STRING_ARRAY) else None
            )
            if not isinstance(paths, list) or paths != _strings(paths):
                raise ValueError(f"Unsupported editor plugin list: {group.strip()}")
            enabled.extend(paths)
    return enabled


def enable_plugins(text: str, plugins: Iterable[str]) -> str:
    """Return project.godot text whose editor plugins also include plugins."""
    enabled = set(plugins) | set(enabled_plugins(text))
    text = "".join(
        group
        for group, section, _ in statement_groups(text)
        if section != "editor_plugins"
    )
    if not enabled:
        return text
    paths = ", ".join(json.dumps(path) for path in sorted(enabled))
    return text.rstrip() + f"\n\n[editor_plugins]\nenabled=PackedStringArray({paths})\n"


# ==== Composition =============================================================


# The purposes of a project.godot: the game's, the context every import reads, the
# configuration packs export and the one editor views open.
PURPOSES = ("runtime", "import", "export", "editor")


@dataclasses.dataclass(frozen=True)
class _Purpose:
    """The settings a purpose's project.godot carries; see compose_project."""

    name: str
    kinds: dict[str, dict]
    sections: Iterable[str] | None
    active_features: Collection[str] | None
    context_only: bool

    def carries(self, section: str | None, key: str, literal: str) -> bool:
        """Whether the purpose carries a statement of section and key with literal."""
        if section == "editor_plugins":
            return False
        kind = setting_kind(setting_key(section, key), self.kinds, self.sections)
        if kind is not None and not self._carries_kind(kind, literal):
            return False
        # An override with no tag the editor of import actions has cannot affect an import.
        return self.name != "import" or override_applies(key, self.active_features)

    def _carries_kind(self, kind: dict, literal: str) -> bool:
        if self.name not in kind["purposes"]:
            return False
        return not (self.context_only and _names_game_files(kind, literal))


def _replacements(
    settings: dict[str, str], autoloads: dict[str, str], main_scene: str
) -> dict[str, str]:
    """The settings a composition sets, to their validated or quoted Godot literals."""
    replacements = {key: validate_literal(value) for key, value in settings.items()}
    replacements.update(
        {
            "autoload/" + name: json.dumps(value, ensure_ascii=False)
            for name, value in autoloads.items()
        }
    )
    if main_scene:
        replacements["application/run/main_scene"] = json.dumps(
            main_scene, ensure_ascii=False
        )
    return replacements


def _empty_header(group: str, section: str | None, filled: set[str | None]) -> bool:
    """Whether group is the header of a section none of whose settings stay."""
    return section not in filled and SECTION.match(group.strip()) is not None


def _authored_settings(base: str, purpose: _Purpose, dropped: set[str]) -> str:
    """The statements of base the purpose carries, except the dropped settings."""
    kept = []
    filled = set()
    for group in statement_groups(base):
        text, section, key = group
        if key is not None:
            setting = setting_key(section, key)
            if setting in dropped or not purpose.carries(
                section, key, statement_value(text).strip()
            ):
                continue
            filled.add(section)
        kept.append(group)
    # A section none of whose settings the purpose carries leaves with its header.
    return (
        "".join(
            group
            for group, section, _ in kept
            if not _empty_header(group, section, filled)
        ).rstrip()
        + "\n"
    )


def _added_settings(replacements: dict[str, str], purpose: _Purpose) -> str:
    """The sections that append the replacements the purpose carries, in setting order."""
    statements: dict[str, list[str]] = {}
    for setting, value in sorted(replacements.items()):
        section, key = setting.split("/", 1)
        if purpose.carries(section, key, value):
            statements.setdefault(section, []).append(f"{key}={value}\n")
    return "".join(
        f"\n[{section}]\n" + "".join(lines) for section, lines in statements.items()
    )


def compose_project(
    base: str,
    settings: dict[str, str],
    autoloads: dict[str, str],
    main_scene: str,
    *,
    purpose: str = "runtime",
    editor_plugins: list[str] | None = None,
    active_features: set[str] | None = None,
    kinds: dict[str, dict] | None = None,
    sections: Iterable[str] | None = None,
    excluded: Iterable[str] = (),
    context_only: bool = False,
    pinned: dict[str, str] | None = None,
) -> str:
    """
    Construct a purpose's project.godot from the authored base and explicit contributions.

    A setting reaches the purpose when its kind carries the purpose, and a setting of
    no kind when it is Godot's own or the purpose is not import. Editor plugins come
    only from editor_plugins.

    Args:
        base: Authored project.godot text.
        settings: section/property keys to Godot literal values.
        autoloads: Autoload names to res:// paths.
        main_scene: res:// path of the main scene, or empty.
        purpose: "runtime" for the runtime configuration, "import" for the
            context of import actions, "export" for the configuration a pack
            exports, "editor" for the configuration of an editor view.
        editor_plugins: plugin.cfg res:// paths the purpose enables; not for runtime
            or import, which enable no plugin.
        active_features: Feature tags the editor of import actions has; None keeps
            every feature override.
        kinds: The setting-kind table of the engine version; None classifies no
            setting as naming a file.
        sections: The sections of Godot's own settings; None knows every key.
        excluded: Settings of base to leave out, such as those left_out returns for
            the view's members.
        context_only: Whether the configuration carries no setting that names a file of
            the game, as the shell-assets probe's, which stages no game: no content-bound
            setting of Godot and no unknown key whose value names a res:// path.
        pinned: Settings the ruleset fixes, to Godot literals: each replaces the authored
            setting and every feature override of it, which Starlark's validation keeps
            the contributions from contradicting.

    An authored root _custom_features key never stays: custom features come only from
    the project's build settings, and only exports and source runs have them.

    Returns:
        The constructed project.godot text.
    """
    if purpose not in PURPOSES:
        raise ValueError(f"Unknown project purpose: {purpose!r}")
    if editor_plugins and purpose in ("runtime", "import"):
        raise ValueError(f"Editor plugins are not enabled for the {purpose} purpose")
    carrier = _Purpose(purpose, kinds or {}, sections, active_features, context_only)
    pinned = pinned or {}
    replacements = _replacements(settings | pinned, autoloads, main_scene)
    dropped = {"_custom_features", *excluded, *replacements, *_overrides_of(base, pinned)}
    text = _authored_settings(base, carrier, dropped) + _added_settings(
        replacements, carrier
    )
    return enable_plugins(text, editor_plugins) if editor_plugins else text


# ==== Write back ==============================================================


def _statements(text: str) -> dict[str, str]:
    """Map each setting to its statement, ending in a newline; the last one wins."""
    return {
        setting_key(section, key): group if group.endswith("\n") else group + "\n"
        for group, section, key in statement_groups(text)
        if key is not None
    }


def _setting_value(statements: dict[str, str], setting: str) -> str | None:
    statement = statements.get(setting)
    return None if statement is None else statement_value(statement).strip()


def _insert(
    groups: list[tuple[str, str | None, str | None]], setting: str, statement: str
) -> str:
    """Add the statement of a setting groups lack to its section, opening it if needed."""
    section = setting_section(setting)
    result = [group for group, _, _ in groups]
    # Insert after the section's last setting, or its header, not after
    # the blank lines that separate it from the next section.
    ends = [
        index + 1
        for index, (group, group_section, key) in enumerate(groups)
        if group_section == section and (key is not None or SECTION.match(group))
    ]
    if ends:
        result.insert(ends[-1], statement)
        return "".join(result)
    if section is None:
        return statement + "".join(result)
    return "".join(result).rstrip() + f"\n\n[{section}]\n\n{statement}"


def _replace(text: str, setting: str, statement: str | None) -> str:
    """Replace, insert or, for None, remove one setting's statement in text."""
    groups = statement_groups(text)
    assigns = [
        key is not None and setting_key(section, key) == setting
        for _, section, key in groups
    ]
    if not any(assigns):
        return text if statement is None else _insert(groups, setting, statement)
    # The first statement of the setting becomes the new one; any later one leaves.
    result = [group for (group, _, _), match in zip(groups, assigns) if not match]
    if statement is not None:
        result.insert(assigns.index(True), statement)
    return "".join(result)


@dataclasses.dataclass
class WriteBack:
    """Authored text after a write-back, and what was written or only reported."""

    text: str
    written: list[str]
    reported: list[str]


def write_back(
    authored: str, baseline: str, edited: str, composed: dict[str, str]
) -> WriteBack:
    """
    Carry setting changes made in an editor view back to the authored project.godot.

    Args:
        authored: The authored project.godot text as it is now.
        baseline: The view's project.godot as it was composed.
        edited: The view's project.godot after editing.
        composed: Settings the composition sets to the label that declares them;
            the editor plugin activation always belongs to the project.

    Returns:
        The new authored text, the settings written to it, and a message for each
        change it does not take: composed settings, and settings that also
        changed in the authored file.
    """
    before = _statements(baseline)
    after = _statements(edited)
    current = _statements(authored)
    written = []
    reported = []
    for setting in sorted(before.keys() | after.keys()):
        old = _setting_value(before, setting)
        if old == _setting_value(after, setting):
            continue
        # The editor purpose enables the plugins of the project's add-ons.
        section = setting_section(setting)
        if setting in composed or section == "editor_plugins":
            owner = composed.get(setting, f"the project's {section}")
            reported.append(f"{setting} is set by {owner}; change it there")
            continue
        if _setting_value(current, setting) != old:
            reported.append(
                f"{setting} changed in the editor and in the authored project.godot; "
                "kept the authored value"
            )
            continue
        authored = _replace(authored, setting, after.get(setting))
        written.append(setting)
    return WriteBack(authored, written, reported)
