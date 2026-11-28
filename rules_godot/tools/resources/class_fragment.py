"""
The global script classes of one unit's scripts, and the class cache Godot reads from them.

A fragment holds, for each GDScript file of a unit, the header Godot's editor scan reads:
its class_name, its base as written, its @tool, @abstract and @icon annotations and the
bases of its inner classes. A validation merges the fragments of a unit's closure into
`.godot/global_script_class_cache.cfg`, so its Godot process resolves the closure's classes
before, and without, an editor scan. A base written as a script path resolves through that
script's fragment, as Godot's scan does.
"""

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

from tools.inputs.mapped_paths import add_root_arguments, resolve_paths, resolver
from tools.resources.text import is_identifier, is_punctuation, tokens

CACHE = ".godot/global_script_class_cache.cfg"

# What a script extends: a name chain such as Node or Outer.Inner, or a script path with
# the inner class chain after it.
Base = dict


# How each bracket changes the nesting of arguments. Only punctuation counts, not a string
# with the same text.
_NESTING = {"(": 1, ")": -1}


def skip_arguments(script: list, index: int) -> int:
    """Return the index after the parenthesized arguments that open at script[index]."""
    depth = 0
    for position in range(index, len(script)):
        category, value = script[position][:2]
        depth += _NESTING.get(value, 0) if category == "punctuation" else 0
        if not depth:
            return position + 1
    return len(script)


def _continues_chain(script: list, index: int) -> bool:
    """Whether script[index] starts `.Name`, the next link of a name chain."""
    return (
        index + 1 < len(script)
        and script[index][1] == "."
        and script[index + 1][0] == "identifier"
    )


def _base(script: list, index: int) -> tuple[Base, int]:
    """Read the base after `extends` at script[index]; return it and the next index."""
    path = None
    names = []
    if index < len(script) and script[index][0] == "string":
        path = script[index][1]
        index += 1
    elif index < len(script) and script[index][0] == "identifier":
        names.append(script[index][1])
        index += 1
    while _continues_chain(script, index):
        names.append(script[index + 1][1])
        index += 2
    return {"path": path, "names": names}, index


def _icon(script: list, index: int) -> str | None:
    """
    The path of the @icon whose arguments open at script[index], or None.

    Godot's editor scan records an icon only for a single string argument that a `)`
    closes, with or without a comma between them. It records none for `@icon(`, an
    unclosed `@icon("x"` or two arguments.
    """
    if index + 1 >= len(script) or script[index + 1][0] != "string":
        return None
    end = index + 2
    if end < len(script) and is_punctuation(script[end], ","):
        end += 1
    closed = end < len(script) and is_punctuation(script[end], ")")
    return script[index + 1][1] if closed else None


def _annotation(script: list, index: int) -> tuple[str, str | None, int]:
    """
    Read the annotation whose name is at script[index].

    Returns its name, the path of an `@icon("path")` or else None, and the next index.
    """
    name = script[index][1]
    index += 1
    if index >= len(script) or not is_punctuation(script[index], "("):
        return name, None, index
    icon = _icon(script, index) if name == "icon" else None
    return name, icon, skip_arguments(script, index)


def _declaration(script: list, index: int, header: dict) -> int:
    """Read the class_name or extends at script[index] into header; return the next index."""
    if script[index][1] == "extends":
        header["base"], index = _base(script, index + 1)
        return index
    if index + 1 < len(script) and script[index + 1][0] == "identifier":
        header["class"] = script[index + 1][1]
    return index + 2


def _script_class(script: list, header: dict) -> int:
    """Read the script's own annotations, class_name and extends; return where they end."""
    abstract = False
    index = 0
    while index < len(script):
        category, value, _ = script[index]
        if value == "@" and index + 1 < len(script):
            annotation, icon, index = _annotation(script, index + 1)
            if icon is not None:
                header["icon"] = icon
            header["is_tool"] |= annotation == "tool"
            abstract |= annotation == "abstract"
        elif category == "identifier" and value in ("class_name", "extends"):
            index = _declaration(script, index, header)
            # An @abstract before class_name or extends belongs to the class.
            header["is_abstract"] |= abstract
            abstract = False
        else:
            # The first member ends the header; its annotations are the member's.
            break
    return index


def _inner_bases(script: list, index: int) -> dict[str, Base | None]:
    """The bases of the inner classes declared from script[index] on, by class name."""
    inner = {}
    for position in range(index, len(script) - 2):
        if (
            is_identifier(script[position], "class")
            and script[position + 1][0] == "identifier"
        ):
            base = None
            if is_identifier(script[position + 2], "extends"):
                base, _ = _base(script, position + 3)
            inner.setdefault(script[position + 1][1], base)
    return inner


def script_header(text: str) -> dict:
    """
    Read the header Godot's editor scan reads from a GDScript file.

    Args:
        text: The script's source.

    Returns:
        A dict of class (the class_name or empty), base (Base, or None without extends),
        is_tool, is_abstract, icon and inner, the bases of the inner classes by name.
    """
    script = [token for token in tokens(text) if token[0] != "newline"]
    header = {
        "class": "",
        "base": None,
        "is_tool": False,
        "is_abstract": False,
        "icon": "",
        "inner": {},
    }
    header["inner"] = _inner_bases(script, _script_class(script, header))
    return header


def fragment(scripts: dict[str, str]) -> list[dict]:
    """
    Return a unit's fragment: the header of each script, by resource path.

    Args:
        scripts: Resource paths, without res://, to the scripts' sources.

    Returns:
        The headers with their res:// path, in path order.
    """
    return [
        {"path": "res://" + path} | script_header(text)
        for path, text in sorted(scripts.items())
    ]


def _resolve(
    base: Base | None, scripts: dict[str, dict], visiting: frozenset[str]
) -> str:
    """The base Godot records for a script or inner class that extends base."""
    if base is None:
        return "RefCounted"
    path = base["path"]
    names = base["names"]
    if path is None:
        # A chain such as Outer.Inner records no base.
        return names[0] if len(names) == 1 else ""
    # A script path followed by a chain of inner classes records no base either.
    if len(names) > 1:
        return ""
    # Godot opens the path as written, so a relative path names no script it scans.
    parent = scripts.get(path)
    if parent is None or path in visiting:
        return ""
    visiting = visiting | {path}
    if not names:
        return _resolve(parent["base"], scripts, visiting)
    if names[0] not in parent["inner"]:
        return ""
    return _resolve(parent["inner"][names[0]], scripts, visiting)


def _string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _boolean(value: bool) -> str:
    return "true" if value else "false"


def _cache_entry(script: dict, scripts: dict[str, dict], is_tool: bool) -> str:
    """The class cache's entry for a named script, as Godot writes it."""
    return (
        "{\n"
        + f'"base": &{_string(_resolve(script["base"], scripts, frozenset()))},\n'
        + f'"class": &{_string(script["class"])},\n'
        + f'"icon": {_string(script["icon"])},\n'
        + f'"is_abstract": {_boolean(script["is_abstract"])},\n'
        + f'"is_tool": {_boolean(is_tool)},\n'
        + '"language": &"GDScript",\n'
        + f'"path": {_string(script["path"])}\n'
        + "}"
    )


def class_cache(fragments: Iterable[list[dict]], tool_annotations: bool = True) -> str:
    """
    Merge fragments into the global_script_class_cache.cfg text Godot's scan writes.

    Args:
        fragments: The fragments of a closure, each a list of script headers.
        tool_annotations: Whether the scripts Godot loads keep the @tool the fragments
            record; False for copies that lost it, such as a validation's, whose
            entries are then no tool scripts.

    Returns:
        The cache's text: one entry per named script, by class name.
    """
    scripts = {script["path"]: script for each in fragments for script in each}
    entries = [
        _cache_entry(script, scripts, tool_annotations and script["is_tool"])
        for script in sorted(
            scripts.values(), key=lambda script: (script["class"], script["path"])
        )
        if script["class"]
    ]
    return "list=[" + ", ".join(entries) + "]\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    add_root_arguments(parser)
    args = parser.parse_args()
    scripts = resolve_paths(
        json.loads(args.manifest.read_text(encoding="utf-8")), resolver(args.roots)
    )
    sources = {}
    for path, source in scripts.items():
        try:
            sources[path] = Path(source).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            sys.exit(f"res://{path}: not valid UTF-8, as which Godot reads scripts")
    args.output.write_text(
        json.dumps(
            fragment(sources),
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
