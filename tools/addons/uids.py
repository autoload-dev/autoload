"""Godot resource UIDs as text, for the example projects the generator writes."""

# ResourceUID's digits: 'a' to 'z', then '0' to '9' from 'z' on, as Godot's char_count is
# 'z' - 'a' = 25 (core/io/resource_uid.cpp:44-45, 92-111 in Godot 4.7.2). The ruleset's
# tools/resource_uids.py reads and writes them for builds; this copy keeps the repository's
# tooling independent of the ruleset.
_UID_BASE = 34
# The digits ResourceUID::id_to_text writes, by value.
_UID_DIGITS = "abcdefghijklmnopqrstuvwxy012345678"


def is_uid(text: str) -> bool:
    """Whether ResourceUID::text_to_id reads an ID from text."""
    digits = text.removeprefix("uid://")
    return (
        text.startswith("uid://")
        and bool(digits)
        and all("a" <= c <= "z" or "0" <= c <= "9" for c in digits)
    )


def id_to_uid(value: int) -> str:
    """Return the uid:// text ResourceUID::id_to_text writes for a non-negative ID."""
    if value < 0:
        raise ValueError(f"Not a resource ID: {value}")
    digits = ""
    while True:
        value, digit = divmod(value, _UID_BASE)
        digits = _UID_DIGITS[digit] + digits
        if not value:
            return "uid://" + digits
