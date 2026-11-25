"""
The content validation of one unit: its scripts and scenes loaded under its closure.

The action stages the unit's closure with its import results and the extensions of the
add-ons it uses, writes the closure's global script classes from their class fragments
into it and, into the context's import configuration, the autoloads of the closure's
runtime configuration whose files the closure holds: the authored project.godot's and
the declared ones. It loads the unit's scripts and then its scenes in one Godot process.
The errors and warnings Godot reports while each file loads decide: any error fails the
unit, and a reference whose UID is stale fails only where
//godot/metadata:resource_uids requires UIDs. It is a separate tool from the other
actions', so a change to it reruns only validations.

The validation checks code and runs none of it. Godot runs in editor mode, which disables
scripting for every script but a tool script, and validate.gd checks the files before the
editor's first filesystem scan starts. So that no tool script runs either, the staged copies
of the closure's scripts and of the scripts built into its text scenes and resources lose
their tool annotations, removed so that every line keeps its number, and the validation
enables no editor plugin. A staged script, scene or resource that is no UTF-8 text, as
Godot reads them, keeps its annotations, so it fails the validation before Godot starts. Godot instantiates every autoload of project.godot at startup, so
each autoload there names a stub scene, an empty Node: Godot registers the name and
instantiates only the stub. Before the first file loads, validate.gd gives each autoload
back the path the analyzer types it by, which for a scene is its root node's script.

Sections: Autoloads, Tool mode, Findings, Validation.
"""

import argparse
import contextlib
import json
import re
import shutil
import string
import sys
from collections.abc import Container, Iterable, Iterator, Sequence
from pathlib import Path

from godot.private.project_config import compose_project
from tools.class_fragment import CACHE, class_cache
from tools.godot_staging import (
    ACTION_DIRECTORY,
    Original,
    add_manifest_arguments,
    join_action,
    load_manifest,
    run_action,
    staged_project,
)
from tools.resource_graph import Heading, Token, headings, lex, res_path
from tools.resource_uids import known_uids, uid_sources


def _singleton(value: str) -> str:
    """The singleton `*` of an autoload's value, if it has one."""
    return "*" if value.startswith("*") else ""


def _section_end(text: str, sections: list[Heading], index: int) -> int:
    """Where the properties of a text scene or resource's section end."""
    return sections[index + 1].body if index + 1 < len(sections) else len(text)


# ==== Autoloads ===============================================================

_SCENES = (".tscn", ".scn")
_EXT_RESOURCE = r'ExtResource\(\s*"?([^")\s]+)"?\s*\)'
_SCRIPT_PROPERTY = re.compile(r"^script\s*=\s*" + _EXT_RESOURCE, re.MULTILINE)


def _is_text_scene(source: Path, scene: str) -> bool:
    return scene.endswith(".tscn") and source.is_file()


def _ext_resource_paths(sections: list[Heading], scene: str) -> dict[str | None, str]:
    """The res:// paths of a scene's external resources by ID."""
    paths = {}
    for heading in sections:
        if heading.section != "ext_resource" or "path" not in heading.attrs:
            continue
        with contextlib.suppress(ValueError):
            paths[heading.attrs.get("id")] = res_path(heading.attrs["path"], scene)
    return paths


def _root_node(sections: list[Heading]) -> int | None:
    """The index of a scene's root node section, if it has one."""
    return next(
        (
            index
            for index, heading in enumerate(sections)
            if heading.section == "node" and "parent" not in heading.attrs
        ),
        None,
    )


def _root_script(
    root: Path, scene: str, seen: frozenset[str] = frozenset()
) -> str | None:
    """
    The res:// path of the script on a staged text scene's root node, or None.

    The root of an inherited scene without a script of its own has its base scene's. None
    for a root without a script or with a built-in one, and for a scene that is not staged
    text.
    """
    source = root / scene.removeprefix("res://")
    if scene in seen or not _is_text_scene(source, scene):
        return None
    text = source.read_text(encoding="utf-8", errors="replace")
    sections = list(headings(text))
    paths = _ext_resource_paths(sections, scene)
    index = _root_node(sections)
    if index is None:
        return None
    heading = sections[index]
    script = _SCRIPT_PROPERTY.search(
        text, heading.end, _section_end(text, sections, index)
    )
    if script:
        return paths.get(script[1])
    base = re.fullmatch(_EXT_RESOURCE, heading.attrs.get("instance", ""))
    if base and base[1] in paths:
        return _root_script(root, paths[base[1]], seen | {scene})
    return None


def _typed_value(root: Path, value: str) -> str | None:
    """The value of one autoload that validate.gd sets; None for a scene without one."""
    path = value.removeprefix("*")
    if not path.endswith(_SCENES):
        return value
    script = _root_script(root, path)
    return _singleton(value) + script if script else None


def typed_autoloads(root: Path, autoloads: dict[str, str]) -> dict[str, str]:
    """
    The autoload values validate.gd sets before the first file loads.

    The GDScript analyzer types a singleton by its script, and a scene singleton by the
    script of the node Godot instantiated for it, which is the stub's none. So a script
    keeps its value and a scene gets its root node's script, with the singleton `*`.

    Args:
        root: The staged project.
        autoloads: The autoloads of the validation, name to value as in project.godot.

    Returns:
        The values by name; a scene without a root script has none and stays a Node.
    """
    return {
        name: typed
        for name, value in autoloads.items()
        if (typed := _typed_value(root, value)) is not None
    }


def closure_autoloads(
    authored: dict[str, str],
    declared: dict[str, str],
    uids: dict[str, str],
    members: Container[str],
) -> dict[str, str]:
    """
    The autoloads of the closure's runtime configuration, name to value with a res:// path.

    A declared autoload replaces the authored one of its name, as in a view's
    configuration. A uid:// value, as Godot's editor writes autoloads, resolves through
    the UIDs the staged files declare. An autoload whose file the closure lacks stays
    out, as views leave it out, and so does one whose UID names no file of the closure;
    a declared one left out leaves the authored one of its name in place, as in a view.

    Args:
        authored: The autoloads of the authored project.godot, as
            project_config.authored_autoloads lists them.
        declared: The add-ons' autoloads, the project's own and its overrides, merged.
        uids: The UIDs of the staged files by res:// path.
        members: The resource paths of the staged closure.

    Returns:
        The values by name, with the singleton `*` they had.
    """
    paths = {uid: path for path, uid in uids.items()}

    def held(autoloads: dict[str, str]) -> dict[str, str]:
        result = {}
        for name, value in autoloads.items():
            path = value.removeprefix("*")
            path = paths.get(path, "") if path.startswith("uid://") else path
            if path.startswith("res://") and path.removeprefix("res://") in members:
                result[name] = _singleton(value) + path
        return result

    autoloads = held(authored)
    autoloads.update(held(declared))
    return autoloads


# ==== Tool mode ===============================================================

# The annotations that make the editor run a script: @tool, and @export_tool_button, which
# the analyzer accepts only in a tool script.
_TOOL_ANNOTATIONS = ("tool", "export_tool_button")
# The files whose scripts lose their tool annotations: scripts, and text scenes and
# resources with scripts built in.
_SCRIPTED = (".gd", ".tscn", ".tres")
_BUILT_IN_SOURCE = re.compile(r'^script/source\s*=\s*"', re.MULTILINE)
# The escapes of Godot's text resource strings that name another character; any other
# escaped character stands for itself, as core/variant/variant_parser.cpp reads them.
_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r"}
_TRAIL_SURROGATE = re.compile(r"\\u([dD][c-fC-F][0-9a-fA-F]{2})")


def _is_punctuation(token: Token, value: str) -> bool:
    return token.category == "punctuation" and token.value == value


def _is_parenthesis(token: Token) -> bool:
    return token.category == "punctuation" and token.value in "()"


def _annotates_tool(at: Token, name: Token) -> bool:
    """Whether two tokens are an annotation that makes the editor run a script."""
    if not _is_punctuation(at, "@") or name.category != "identifier":
        return False
    return name.start == at.end and name.value in _TOOL_ANNOTATIONS


def _arguments_end(arguments: list[Token], end: int) -> int:
    """Where the parenthesized arguments that follow an annotation end, or else end."""
    if not arguments or not _is_punctuation(arguments[0], "("):
        return end
    depth = 0
    for token in filter(_is_parenthesis, arguments):
        depth += 1 if token.value == "(" else -1
        if not depth:
            return token.end
    return end


def _tool_spans(source: str) -> Iterator[tuple[int, int]]:
    """
    The spans of a GDScript source's tool annotations, an @export_tool_button's arguments
    included.

    Only annotation tokens count, so the words in strings and comments stay; the lexer of
    tools/resource_graph.py is no GDScript parser, so a source it misreads, such as one
    with an unterminated string, may keep an annotation or lose an unrelated `@tool`.
    """
    script = [token for token in lex(source) if token.category != "newline"]
    for index, at in enumerate(script[:-1]):
        name = script[index + 1]
        if _annotates_tool(at, name):
            yield at.start, _arguments_end(script[index + 2 :], name.end)


def _unicode_escape(text: str, position: int, digits: int) -> tuple[str, int] | None:
    """
    Read the code of a \\u or \\U escape that starts at position.

    Returns:
        The character and the position after the escape, a trailing surrogate's
        included; None for a malformed code.
    """
    code = text[position : position + digits]
    if len(code) != digits or not all(c in string.hexdigits for c in code):
        return None
    position += digits
    character = int(code, 16)
    if not 0xD800 <= character < 0xDC00:
        return chr(character), position
    trail = _TRAIL_SURROGATE.match(text, position)
    if not trail:
        return None
    character = 0x10000 + ((character - 0xD800) << 10) + int(trail[1], 16) - 0xDC00
    return chr(character), trail.end()


def _escape(text: str, position: int) -> tuple[str, int] | None:
    """Read the escape whose letter is at position, after its backslash."""
    escape = text[position]
    digits = {"u": 4, "U": 6}.get(escape)
    if not digits:
        return _ESCAPES.get(escape, escape), position + 1
    return _unicode_escape(text, position + 1, digits)


def _character(text: str, position: int) -> tuple[str, int] | None:
    """Read one character of a string literal; return it and the position after it."""
    if text[position] != "\\" or position + 1 == len(text):
        return text[position], position + 1
    return _escape(text, position + 1)


def _decode(text: str, start: int) -> tuple[str, list[int]] | None:
    """
    Read a text resource's string literal whose content starts at start.

    Returns:
        Its value and, per character and one past the last, its offset in text; None for
        an unterminated string or a malformed hexadecimal escape, which Godot rejects.
    """
    value, offsets = [], []
    position = start
    while position < len(text) and text[position] != '"':
        offsets.append(position)
        read = _character(text, position)
        if read is None:
            return None
        character, position = read
        value.append(character)
    if position == len(text):
        return None
    offsets.append(position)
    return "".join(value), offsets


def _built_in_sources(text: str) -> Iterator[tuple[str, list[int]]]:
    """
    The sources of the GDScripts built into a text scene or resource.

    Yields:
        Each source and, per character and one past the last, its offset in text.
    """
    sections = list(headings(text))
    for index, heading in enumerate(sections):
        if heading.section != "sub_resource" or heading.attrs.get("type") != "GDScript":
            continue
        end = _section_end(text, sections, index)
        found = _BUILT_IN_SOURCE.search(text, heading.end, end)
        decoded = found and _decode(text, found.end())
        if decoded:
            yield decoded


def _blanks_end(source: str, end: int) -> int:
    """Where the spaces and tabs from end on end."""
    while end < len(source) and source[end] in " \t":
        end += 1
    return end


def _replacement(character: str, indentation: str) -> str:
    """What replaces a character of an annotation that leaves: only line breaks stay."""
    if character == "\n":
        return "\n" + indentation
    return "\r" if character == "\r" else ""


def _removed(
    source: str, start: int, end: int, indentation: str
) -> Iterator[tuple[int, str]]:
    """The edits that remove an annotation with the blanks after it, by index."""
    end = _blanks_end(source, end)
    last = source.rfind("\n", start, end)
    for index in range(start, end):
        yield index, _replacement(source[index], indentation if index == last else "")


def _tool_edits(source: str) -> Iterator[tuple[int, str]]:
    """
    What replaces each character of a GDScript source's tool annotations, by index.

    Every line keeps its number. An annotation after other code on its line becomes
    spaces, so the columns after it stay too. One that starts its line leaves with the
    blanks after it, as GDScript reads leading blanks as indentation, and the code after
    a multi-line one gets the indentation of the line it started on.
    """
    for start, end in _tool_spans(source):
        line = source.rfind("\n", 0, start) + 1
        before = source[line:start]
        if before.strip() and "\n" not in source[start:end]:
            yield from ((index, " ") for index in range(start, end))
            continue
        indentation = before[: len(before) - len(before.lstrip())]
        yield from _removed(source, start, end, indentation)


def without_tool_mode(path: str, text: str) -> str:
    """
    A staged script, scene or resource whose scripts have no tool annotation.

    Args:
        path: The file's resource path, which tells a script from a scene or resource.
        text: The file's text.

    Returns:
        The text without the tool annotations of the script or of its built-in scripts,
        whose lines keep their numbers.
    """
    if path.endswith(".gd"):
        sources: Iterator[tuple[str, Sequence[int]]] = iter(
            [(text, range(len(text) + 1))]
        )
    else:
        sources = _built_in_sources(text)
    pieces, last = [], 0
    for source, offsets in sources:
        for index, replacement in _tool_edits(source):
            pieces += [text[last : offsets[index]], replacement]
            last = offsets[index + 1]
    return "".join(pieces) + text[last:]


def remove_tool_mode(root: Path, staged: Iterable[str]) -> list[str]:
    """
    Remove the tool annotations from the staged files' scripts; see without_tool_mode.

    Args:
        root: The staged project.
        staged: The staged files' resource paths.

    Returns:
        The res:// paths of the scripts, scenes and resources that are no UTF-8 text,
        whose annotations stay: Godot reads them as UTF-8, so no Godot process may load
        them.
    """
    undecodable = []
    for path in staged:
        if not path.endswith(_SCRIPTED) or path.startswith(".godot/"):
            continue
        file = root / path
        try:
            text = file.read_text(encoding="utf-8", newline="")
        except UnicodeDecodeError:
            undecodable.append("res://" + path)
            continue
        blanked = without_tool_mode(path, text)
        if blanked != text:
            file.write_text(blanked, encoding="utf-8", newline="")
    return sorted(undecodable)


# ==== Findings ================================================================

# Godot's warning for a reference whose uid names no known file while its path does.
_STALE_UID = "invalid UID"


def _describe(subject: str, finding: dict) -> str:
    """One finding as path:line: text, with Godot's own source for its engine errors."""
    if finding["file"] == subject:
        return f"{subject}:{finding['line']}: {finding['text']}"
    return f"{subject}: {finding['text']} ({finding['file']}:{finding['line']})"


def verdict(findings: dict[str, list[dict]], resource_uids: str) -> dict[str, list[str]]:
    """
    Sort the findings of a validation into failures and warnings.

    Args:
        findings: What Godot reported while each file loaded, by res:// path.
        resource_uids: The value of //godot/metadata:resource_uids.

    Returns:
        A dict of failures and warnings, each a list of described findings in file order.
    """
    result: dict[str, list[str]] = {"failures": [], "warnings": []}
    for subject, entries in sorted(findings.items()):
        for finding in entries:
            stale = _STALE_UID in finding["text"]
            failing = finding["type"] != "warning" or (
                stale and resource_uids == "require"
            )
            result["failures" if failing else "warnings"].append(
                _describe(subject, finding)
            )
    return result


def absent_extensions_hint(descriptors: list[str]) -> str:
    """Name the extensions the validation left out, which may explain its failures."""
    return (
        "These extensions have no library for the platform this configuration builds, so "
        "the validation did not load them, as that platform's runtime cannot: "
        + ", ".join(f"res://{path}" for path in descriptors)
        + ". A script that uses their classes cannot run there. Guard the use with "
        "ClassDB, give the extension a library for the platform, or leave it out of "
        "the platform's deps."
    )


def toolless_extensions_hint(descriptors: list[str]) -> str:
    """Name the extensions without a library on the execution platform of the validation."""
    return (
        "These extensions have no library in the tool configuration of this "
        "validation's execution platform, so its editor did not load them: "
        + ", ".join(f"res://{path}" for path in descriptors)
        + ". Guard the use with ClassDB, or give the extension's "
        "@autoload_rules_godot//godot:tool branch a library for that platform, such as "
        "linux/x86_64 for BuildBuddy's executors."
    )


def extensions_hint(manifest: dict) -> str:
    """Name the extensions a failed validation did not load, which may explain its failures."""
    hints = []
    if absent := manifest.get("absent_extensions"):
        hints.append(absent_extensions_hint(absent))
    if toolless := manifest.get("toolless_extensions"):
        hints.append(toolless_extensions_hint(toolless))
    return "\n".join(hints)


# ==== Validation ==============================================================

_VALIDATE = Path(__file__).parent / "validation" / "validate.gd"
_NOT_UTF8 = (
    "not valid UTF-8, as which Godot reads scripts, scenes and resources; the "
    "validation loads no file until it is"
)
# What every autoload names in the validation's project.godot: a Node without a script.
_STUB = "autoload_stub.tscn"
_STUB_SCENE = '[gd_scene format=3]\n\n[node name="AutoloadStub" type="Node"]\n'


def _uids(root: Path, staged: set[str]) -> dict[str, str]:
    """The UIDs the staged files and import results declare, by res:// path."""
    files = uid_sources(
        {
            path.relative_to(root).as_posix(): path
            for path in root.rglob("*")
            if path.is_file()
            and not path.relative_to(root).as_posix().startswith(".godot/")
        }
    )
    return {
        "res://" + path: uid for path, uid in sorted(known_uids(files, staged).items())
    }


def _stub_autoloads(root: Path, autoloads: dict[str, str]) -> None:
    """
    Let every autoload of the staged project.godot name the stub scene.

    The runtime configuration enables no editor plugin, the action's included:
    validate.gd records the result.
    """
    stub = f"res://{ACTION_DIRECTORY}/{_STUB}"
    project = root / "project.godot"
    project.write_text(
        compose_project(
            project.read_text(encoding="utf-8"),
            {},
            {name: _singleton(value) + stub for name, value in autoloads.items()},
            "",
        ),
        encoding="utf-8",
    )


def _load(
    manifest: dict, execroot: Path, staging: tuple[Path, Path, dict[str, Original]]
) -> dict[str, list[dict]]:
    """
    Load the unit's files in the staged project; return what Godot reported per file.

    The closure is every staged file: the members and what the import results and the
    interfaces of the closure's other units hold in place of their scripts and assets.
    """
    work, root, originals = staging
    staged = set(originals)
    fragments = [
        json.loads((execroot / fragment).read_text(encoding="utf-8"))
        for fragment in manifest["fragments"]
    ]
    cache = root / CACHE
    cache.parent.mkdir(parents=True, exist_ok=True)
    # The fragments read the original scripts; the staged copies are no tool scripts.
    cache.write_text(class_cache(fragments, tool_annotations=False), encoding="utf-8")
    uids = _uids(root, staged)
    autoloads = closure_autoloads(
        json.loads(
            (execroot / manifest["authored_autoloads"]).read_text(encoding="utf-8")
        ),
        manifest["autoloads"],
        uids,
        staged,
    )
    join_action(
        root,
        work,
        "validate",
        {
            "checked": ["res://" + path for path in manifest["checked"]],
            "uids": uids,
            "autoloads": typed_autoloads(root, autoloads),
        },
    )
    _stub_autoloads(root, autoloads)
    shutil.copyfile(_VALIDATE, root / ACTION_DIRECTORY / _VALIDATE.name)
    (root / ACTION_DIRECTORY / _STUB).write_text(_STUB_SCENE, encoding="utf-8")
    record = run_action(
        manifest,
        execroot,
        root,
        work,
        ["--editor", "--script", f"res://{ACTION_DIRECTORY}/{_VALIDATE.name}"],
    )
    return record["facts"]["findings"]


def validate(manifest: dict, output: Path, execroot: Path) -> None:
    with staged_project(manifest, execroot, "godot-validate-") as staging:
        _, root, staged = staging
        # A file whose tool annotations cannot be removed fails before Godot starts.
        undecodable = remove_tool_mode(root, staged)
        findings = {} if undecodable else _load(manifest, execroot, staging)
    if undecodable:
        result = {
            "failures": [f"{path}: {_NOT_UTF8}" for path in undecodable],
            "warnings": [],
        }
        heading = "the validation cannot read files of its closure"
    else:
        result = verdict(findings, manifest["resource_uids"])
        heading = "Godot reports errors in its scripts or scenes"
    hint = extensions_hint(manifest) if result["failures"] else ""
    output.write_text(
        json.dumps({**result, **({"hint": hint} if hint else {})}, indent=1) + "\n",
        encoding="utf-8",
    )
    if result["failures"] and manifest["mode"] == "fail":
        sys.exit(
            f"{manifest['owner']}: {heading}:\n"
            + "".join(f"  {failure}\n" for failure in result["failures"]).rstrip()
            + (f"\n{hint}" if hint else "")
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_manifest_arguments(parser)
    parser.add_argument(
        "--fragment",
        dest="fragments",
        action="append",
        default=[],
        help="Class fragment of the closure; repeated.",
    )
    args = parser.parse_args()
    manifest = load_manifest(args)
    manifest["fragments"] = args.fragments
    validate(manifest, args.output.absolute(), Path.cwd())


if __name__ == "__main__":
    main()
