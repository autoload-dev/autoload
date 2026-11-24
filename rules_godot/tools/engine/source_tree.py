"""
Paths and files of an extracted engine tree, shared by the configuration and its rendering.

A recipe's pin covers this module, since the configured graph depends on it.
"""

import json
from pathlib import Path

SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".m", ".mm", ".s", ".S", ".swift"}


def write_json(path: Path, value: object, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Upstream builders can depend on ordered SCons Value mappings (for
    # example, module registration). Preserve their insertion order exactly.
    path.write_text(json.dumps(value, indent=indent) + "\n")


def relative(path: object, root: Path) -> str:
    value = Path(str(path).removeprefix("#"))
    if value.is_absolute():
        try:
            return value.relative_to(root).as_posix()
        except ValueError as error:
            raise ValueError(f"Undeclared path outside engine source: {value}") from error
    if ".." in value.parts:
        raise ValueError(f"Path escapes engine source: {value}")
    return value.as_posix()
