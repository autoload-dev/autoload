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

from tools.mapped_paths import add_root_arguments, resolve_paths, resolver
from tools.resource_text import tokens

CACHE = ".godot/global_script_class_cache.cfg"

# What a script extends: a name chain such as Node or Outer.Inner, or a script path with
# the inner class chain after it.
Base = dict


def skip_arguments(script: list, index: int) -> int:
    """Return the index after the parenthesized arguments starting at script[index]."""
    depth = 0
    for position in range(index, len(script)):
        if script[position][1] == "(":
            depth += 1
        elif script[position][1] == ")":
            depth -= 1
            if not depth:
                return position + 1
    return len(script)


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
    while (
        index + 1 < len(script)
        and script[index][1] == "."
        and script[index + 1][0] == "identifier"
    ):
        names.append(script[index + 1][1])
        index += 2
    return {"path": path, "names": names}, index


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
    abstract = False
    index = 0
    while index < len(script):
        category, value, _ = script[index]
        if value == "@" and index + 1 < len(script):
            annotation = script[index + 1][1]
            index += 2
            if index < len(script) and script[index][1] == "(":
                end = skip_arguments(script, index)
                if annotation == "icon" and script[index + 1][0] == "string":
                    header["icon"] = script[index + 1][1]
                index = end
            header["is_tool"] |= annotation == "tool"
            abstract |= annotation == "abstract"
        elif category == "identifier" and value == "class_name":
            if index + 1 < len(script) and script[index + 1][0] == "identifier":
                header["class"] = script[index + 1][1]
            header["is_abstract"] |= abstract
            abstract = False
            index += 2
        elif category == "identifier" and value == "extends":
            header["base"], index = _base(script, index + 1)
            header["is_abstract"] |= abstract
            abstract = False
        else:
            # The first member ends the header; its annotations are the member's.
            break
    for position in range(index, len(script) - 2):
        if script[position][1] == "class" and script[position + 1][0] == "identifier":
            name = script[position + 1][1]
            base = None
            if script[position + 2][1] == "extends":
                base, _ = _base(script, position + 3)
            header["inner"].setdefault(name, base)
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
    # Godot opens the path as written; a relative one is no script it can scan.
    parent = scripts.get(path)
    if parent is None or path in visiting or len(names) > 1:
        return ""
    visiting = visiting | {path}
    if not names:
        return _resolve(parent["base"], scripts, visiting)
    if names[0] not in parent["inner"]:
        return ""
    return _resolve(parent["inner"][names[0]], scripts, visiting)


def _string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


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
        "{\n"
        + f'"base": &{_string(_resolve(script["base"], scripts, frozenset()))},\n'
        + f'"class": &{_string(script["class"])},\n'
        + f'"icon": {_string(script["icon"])},\n'
        + f'"is_abstract": {"true" if script["is_abstract"] else "false"},\n'
        + f'"is_tool": {"true" if tool_annotations and script["is_tool"] else "false"},\n'
        + '"language": &"GDScript",\n'
        + f'"path": {_string(script["path"])}\n'
        + "}"
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
