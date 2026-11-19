"""Fill template files with {NAME} placeholders, as AGENTS.md describes."""

import re
from collections.abc import Mapping
from pathlib import Path

_PLACEHOLDER = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


def fill(template: Path, values: Mapping[str, str]) -> str:
    """
    Fill a template file with values.

    The template's placeholders and the values must match. A placeholder alone
    on its line stands for a block, and an empty block removes the line. Values
    are inserted in one pass, so text with braces stays as it is.
    """
    text = template.read_text(encoding="utf-8")
    placeholders = set(_PLACEHOLDER.findall(text))
    if placeholders != set(values):
        raise ValueError(
            f"{template.name} has the placeholders {sorted(placeholders)}, "
            f"not {sorted(values)}"
        )
    for name, value in values.items():
        if not value:
            text = re.sub(rf"^[ \t]*\{{{name}\}}[ \t]*\n", "", text, flags=re.MULTILINE)
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], text)
