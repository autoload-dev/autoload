"""
The statements of Godot's configuration files, such as project.godot: each assignment or
section header with the text it spans, its section and its key, and the keys of settings.

Several build tools read only this; project_config.py composes settings on top of it, so a
change to the composition reruns none of their actions.
"""

import json
import re

# A section header, such as [application], with its name.
SECTION = re.compile(r"^\s*\[([^]\r\n]+)\]\s*(?:;.*)?$")

# A comment line, such as Godot's "; param=value" header, assigns nothing.
_ASSIGNMENT = re.compile(r'^\s*(?!;)("(?:[^"\\\r\n]|\\.)*"|[^=\r\n]+?)\s*=')


# The closing bracket of each opening one.
CLOSING = {"(": ")", "[": "]", "{": "}"}

_BRACKET_DEPTH = dict.fromkeys(CLOSING, 1) | dict.fromkeys(CLOSING.values(), -1)


class TextScan:
    """Track the string literals and bracket depth of Godot text across lines."""

    def __init__(self) -> None:
        self.quote = False
        self.escape = False
        self.balance = 0

    def in_string(self, char: str) -> bool:
        """Advance past char; whether it belongs to a string literal, quotes included."""
        if not self.quote:
            self.quote = char == '"'
            return self.quote
        self.quote = self.escape or char != '"'
        self.escape = not self.escape and char == "\\"
        return True

    def continues(self, line: str) -> bool:
        """Scan a line up to its comment; whether its statement continues past it."""
        for char in line:
            if self.in_string(char):
                continue
            if char == ";":
                break
            self.balance += _BRACKET_DEPTH.get(char, 0)
        return self.balance != 0 or self.quote


def _decoded_key(key: str) -> str:
    """
    Decode a quoted setting key to the setting key of its unquoted spelling.

    Godot accepts quoted setting keys. Decode the ordinary JSON string form so a quoted
    key has the same setting key as its unquoted spelling. Unrecognized escapes remain
    authored text and are never evaluated here.
    """
    if not key.startswith('"'):
        return key
    try:
        return json.loads(key)
    except ValueError:
        return key


def _statement_start(line: str, section: str | None) -> tuple[str | None, str | None]:
    """The section after a statement's first line, and the key that line assigns."""
    match = SECTION.match(line.strip())
    if match:
        return match.group(1), None
    assignment = _ASSIGNMENT.match(line)
    return section, _decoded_key(assignment.group(1).strip()) if assignment else None


def statement_groups(text: str) -> list[tuple[str, str | None, str | None]]:
    """Preserve authored text while keeping multiline Variant values together."""
    groups = []
    section = None
    pending = []
    pending_key = None
    scan = TextScan()
    for line in text.splitlines(keepends=True):
        if not pending:
            section, pending_key = _statement_start(line, section)
        pending.append(line)
        if not scan.continues(line):
            groups.append(("".join(pending), section, pending_key))
            pending, pending_key = [], None
    if pending:
        raise ValueError("Unterminated statement in base project.godot")
    return groups


def statement_value(text: str) -> str:
    """The value text of an assignment statement; empty for any other statement."""
    match = _ASSIGNMENT.match(text)
    return text[match.end() :] if match else ""


def setting_key(section: str | None, key: str) -> str:
    """The section/property identity of a statement; root keys have no section."""
    return f"{section}/{key}" if section else key


def setting_section(setting: str) -> str | None:
    """The section of a setting_key identity, or None for a root key."""
    section, separator, _ = setting.partition("/")
    return section if separator else None
