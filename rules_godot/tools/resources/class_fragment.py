"""
The global script classes of one unit's scripts, and the class cache Godot reads from them.

A fragment holds, for each GDScript file of a unit, the header Godot's editor scan reads:
its class_name, its base as written, its @tool, @abstract and @icon annotations and its
inner classes with their bases. A validation merges the fragments of a unit's closure into
`.godot/global_script_class_cache.cfg`, so its Godot process resolves the closure's classes
before, and without, an editor scan. A base written as a script path resolves through that
script's fragment, as Godot's scan does.
"""

import argparse
import json
import posixpath
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from tools.inputs.mapped_paths import add_root_arguments, resolve_paths, resolver
from tools.resources.text import (
    Token,
    is_identifier,
    is_punctuation,
    lex,
    string_argument,
)

CACHE = ".godot/global_script_class_cache.cfg"

# What a script extends: a name chain such as Node or Outer.Inner, or a script path with
# the inner class chain after it.
Base = dict


# How each bracket changes the nesting of arguments. Only punctuation counts, not a string
# with the same text.
_NESTING = {"(": 1, ")": -1}


def _arguments_end(script: list, index: int) -> int | None:
    """The index after the `)` that closes the arguments opening at script[index], or None."""
    depth = 0
    for position in range(index, len(script)):
        category, value = script[position][:2]
        depth += _NESTING.get(value, 0) if category == "punctuation" else 0
        if not depth:
            return position + 1
    return None


def skip_arguments(script: list, index: int) -> int:
    """Return the index after the parenthesized arguments that open at script[index]."""
    end = _arguments_end(script, index)
    return len(script) if end is None else end


def _continues_chain(script: list, index: int) -> bool:
    """Whether script[index] starts `.Name`, the next link of a name chain."""
    return (
        index + 1 < len(script)
        and is_punctuation(script[index], ".")
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


def _resumes_header(token: tuple) -> bool:
    """Whether Godot's parser reads the header on at this token: an annotation, class_name or extends."""
    return (
        is_punctuation(token, "@")
        or is_identifier(token, "class_name")
        or is_identifier(token, "extends")
    )


def _after_cut_arguments(script: list, index: int) -> int:
    """Where Godot reads on after arguments that the file cuts off."""
    while index < len(script) and not _resumes_header(script[index]):
        index += 1
    return index


def _annotates_member(name: str) -> bool:
    """Whether an annotation belongs to a member, as @export, @onready and @rpc do."""
    return name.startswith("export") or name in ("onready", "rpc")


def _annotation(script: list, index: int) -> tuple[str | None, str | None, int]:
    """
    Read the annotation whose name is at script[index].

    Returns its name, or None when Godot drops it; the path of an @icon, or None; and the
    next index.
    """
    name = script[index][1]
    index += 1
    if index >= len(script) or not is_punctuation(script[index], "("):
        return name, None, index
    icon = string_argument(script, index) if name == "icon" else None
    end = _arguments_end(script, index)
    if end is not None:
        return name, icon, end
    # Godot drops an annotation whose arguments are cut off, except an icon it still read.
    return (name if icon else None), icon, _after_cut_arguments(script, index + 1)


def _class_annotations(script: list, header: dict) -> tuple[int, bool]:
    """
    Read the annotations that open the script into header.

    Returns where they end and whether @abstract is among them. Godot skips strings
    between them, which serve as comments. A member's annotation ends them; Godot then
    reads it with the class body and takes no class_name or extends after it.
    """
    abstract = False
    index = 0
    while index + 1 < len(script):
        if script[index][0] == "string":
            index += 1
            continue
        if not is_punctuation(script[index], "@"):
            break
        name, icon, after = _annotation(script, index + 1)
        if name is not None and _annotates_member(name):
            break
        index = after
        # Godot keeps the first @icon and reports the others as errors.
        if icon is not None and not header["icon"]:
            header["icon"] = icon
        header["is_tool"] |= name == "tool"
        abstract |= name == "abstract"
    return index, abstract


def _declaration(script: list, index: int, header: dict) -> int:
    """Read the class_name or extends at script[index] into header; return the next index."""
    if script[index][1] == "extends":
        header["base"], index = _base(script, index + 1)
        return index
    if index + 1 < len(script) and script[index + 1][0] == "identifier":
        header["class"] = script[index + 1][1]
    return index + 2


def _script_class(script: list, header: dict) -> int:
    """
    Read the script's own annotations, class_name and extends; return where they end.

    As in Godot's parser, the annotations come first. An annotation after class_name or
    extends ends the header, as does the first member.
    """
    index, abstract = _class_annotations(script, header)
    while index < len(script):
        category, value = script[index][:2]
        if category == "string":
            index += 1
        elif category == "identifier" and value in ("class_name", "extends"):
            index = _declaration(script, index, header)
            # An @abstract before class_name or extends belongs to the class.
            header["is_abstract"] |= abstract
        else:
            break
    return index


def _declares_class(script: list[Token], position: int) -> bool:
    """Whether script[position] declares an inner class, `class Name`."""
    return (
        is_identifier(script[position], "class")
        and script[position + 1].category == "identifier"
    )


def _inner_base(script: list[Token], position: int) -> Base | None:
    """The base of the inner class declared at script[position], or None."""
    # The extends may also stand on the class's next line, after its colon.
    extends = position + 2
    if extends < len(script) and is_punctuation(script[extends], ":"):
        extends += 1
    if extends < len(script) and is_identifier(script[extends], "extends"):
        return _base(script, extends + 1)[0]
    return None


def _indentation(text: str, token: Token) -> int:
    """The width of the blanks that open the token's line."""
    line_start = text.rfind("\n", 0, token.start) + 1
    line = text[line_start : token.start]
    return len(line) - len(line.lstrip(" \t"))


def _inner_classes(text: str, script: list[Token], index: int) -> dict[str, dict]:
    """
    The inner classes declared from script[index] on, by name, each with its base and its
    own inner classes. A class nests in the class above it whose line is less indented.
    """
    classes: dict[str, dict] = {}
    # The classes that a later class may nest in, with the indentation of their lines.
    enclosing = [(-1, classes)]
    for position in range(index, len(script) - 1):
        if not _declares_class(script, position):
            continue
        indentation = _indentation(text, script[position])
        while enclosing[-1][0] >= indentation:
            enclosing.pop()
        declared = enclosing[-1][1].setdefault(
            script[position + 1].value,
            {"base": _inner_base(script, position), "inner": {}},
        )
        enclosing.append((indentation, declared["inner"]))
    return classes


def script_header(text: str) -> dict:
    """
    Read the header Godot's editor scan reads from a GDScript file.

    Args:
        text: The script's source.

    Returns:
        A dict of class (the class_name or empty), base (Base, or None without extends),
        is_tool, is_abstract, icon as written and inner: the inner classes by name, each a
        dict of its base and its own inner classes.
    """
    script = [token for token in lex(text) if token.category != "newline"]
    header = {
        "class": "",
        "base": None,
        "is_tool": False,
        "is_abstract": False,
        "icon": "",
        "inner": {},
    }
    header["inner"] = _inner_classes(text, script, _script_class(script, header))
    return header


# What opens a path that Godot's simplify_path keeps as it is: a scheme such as res://, a
# network share's `//`, a root, or a Windows drive. A drive with a backslash counts only
# before a later slash.
_DRIVE = re.compile(r"[A-Za-z0-9]+://|//|\\\\|[/\\]|[^/:]*:/|[^/:]*:\\(?=.*/)")


def _simplified(path: str) -> str:
    """
    The path as Godot's simplify_path writes it.

    After its drive, backslashes become slashes, and repeated slashes and `.` go. A `..`
    goes with the folder before it, but stays at the start.
    """
    drive = _DRIVE.match(path)
    start = drive.end() if drive else 0
    rest = re.sub("/+", "/", path[start:].replace("\\", "/")).lstrip("/")
    rest = posixpath.normpath(rest) if rest else rest
    return path[:start] + ("" if rest == "." else rest)


def _is_relative(path: str) -> bool:
    """Whether a path starts neither at a root nor with a drive or scheme, as Godot reads it."""
    return not path.startswith(("/", "\\")) and ":/" not in path and ":\\" not in path


def _icon_path(icon: str, script: str) -> str:
    """The icon path Godot's scan records: a relative one joins the script's folder."""
    if icon and _is_relative(icon):
        icon = posixpath.join("res://" + posixpath.dirname(script), icon)
    return _simplified(icon)


def _script_fragment(path: str, text: str) -> dict:
    """The fragment's entry for the script at a resource path, without res://."""
    header = script_header(text)
    header["icon"] = _icon_path(header["icon"], path)
    return {"path": "res://" + path} | header


def fragment(scripts: dict[str, str]) -> list[dict]:
    """
    Return a unit's fragment: the header of each script, by resource path.

    Args:
        scripts: Resource paths, without res://, to the scripts' sources.

    Returns:
        The headers with their res:// path, in path order.
    """
    return [_script_fragment(path, text) for path, text in sorted(scripts.items())]


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
    # Godot opens the path as written, so a relative path names no script it scans.
    declared = scripts.get(path)
    if declared is None or path in visiting:
        return ""
    visiting = visiting | {path}
    # A chain after the path names an inner class of the script, and its inner classes.
    for name in names:
        declared = declared["inner"].get(name)
        if declared is None:
            return ""
    return _resolve(declared["base"], scripts, visiting)


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
