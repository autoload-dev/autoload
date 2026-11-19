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
"""

import argparse
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
    add_manifest_arguments,
    join_action,
    load_manifest,
    run_action,
    staged_project,
)
from tools.resource_graph import headings, lex, res_path
from tools.resource_uids import known_uids, uid_sources

_VALIDATE = Path(__file__).parent / "validation" / "validate.gd"

# Godot's warning for a reference whose uid names no known file while its path does.
_STALE_UID = "invalid UID"

# What every autoload names in the validation's project.godot: a Node without a script.
_STUB = "autoload_stub.tscn"
_STUB_SCENE = '[gd_scene format=3]\n\n[node name="AutoloadStub" type="Node"]\n'
_SCENES = (".tscn", ".scn")
_EXT_RESOURCE = r'ExtResource\(\s*"?([^")\s]+)"?\s*\)'
_SCRIPT_PROPERTY = re.compile(r"^script\s*=\s*" + _EXT_RESOURCE, re.MULTILINE)


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
    if scene in seen or not scene.endswith(".tscn") or not source.is_file():
        return None
    text = source.read_text(encoding="utf-8", errors="replace")
    sections = list(headings(text))
    paths = {}
    for heading in sections:
        if heading.section == "ext_resource" and "path" in heading.attrs:
            try:
                paths[heading.attrs.get("id")] = res_path(heading.attrs["path"], scene)
            except ValueError:
                continue
    for index, heading in enumerate(sections):
        if heading.section != "node" or "parent" in heading.attrs:
            continue
        end = sections[index + 1].body if index + 1 < len(sections) else len(text)
        script = _SCRIPT_PROPERTY.search(text, heading.end, end)
        if script:
            return paths.get(script[1])
        base = re.fullmatch(_EXT_RESOURCE, heading.attrs.get("instance", ""))
        if base and base[1] in paths:
            return _root_script(root, paths[base[1]], seen | {scene})
        return None
    return None


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
    typed = {}
    for name, value in autoloads.items():
        singleton = "*" if value.startswith("*") else ""
        path = value.removeprefix("*")
        if path.endswith(_SCENES):
            script = _root_script(root, path)
            if script:
                typed[name] = singleton + script
        else:
            typed[name] = value
    return typed


# The annotations that make the editor run a script: @tool, and @export_tool_button, which
# the analyzer accepts only in a tool script.
_TOOL_ANNOTATIONS = ("tool", "export_tool_button")
# The files whose scripts lose their tool annotations: scripts, and text scenes and
# resources with scripts built in.
_SCRIPTED = (".gd", ".tscn", ".tres")
_NOT_UTF8 = (
    "not valid UTF-8, as which Godot reads scripts, scenes and resources; the "
    "validation loads no file until it is"
)
_BUILT_IN_SOURCE = re.compile(r'^script/source\s*=\s*"', re.MULTILINE)
# The escapes of Godot's text resource strings that name another character; any other
# escaped character stands for itself, as core/variant/variant_parser.cpp reads them.
_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r"}
_TRAIL_SURROGATE = re.compile(r"\\u([dD][c-fC-F][0-9a-fA-F]{2})")


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
        if (
            at.category != "punctuation"
            or at.value != "@"
            or name.category != "identifier"
            or name.start != at.end
            or name.value not in _TOOL_ANNOTATIONS
        ):
            continue
        end = name.end
        arguments = script[index + 2 :]
        if (
            arguments
            and arguments[0].category == "punctuation"
            and arguments[0].value == "("
        ):
            depth = 0
            for token in arguments:
                if token.category == "punctuation" and token.value in "()":
                    depth += 1 if token.value == "(" else -1
                    if not depth:
                        end = token.end
                        break
        yield at.start, end


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
        if text[position] != "\\" or position + 1 == len(text):
            value.append(text[position])
            position += 1
            continue
        escape = text[position + 1]
        position += 2
        digits = {"u": 4, "U": 6}.get(escape)
        if not digits:
            value.append(_ESCAPES.get(escape, escape))
            continue
        code = text[position : position + digits]
        if len(code) != digits or not all(c in string.hexdigits for c in code):
            return None
        position += digits
        character = int(code, 16)
        if 0xD800 <= character < 0xDC00:
            trail = _TRAIL_SURROGATE.match(text, position)
            if not trail:
                return None
            position = trail.end()
            character = (
                0x10000 + ((character - 0xD800) << 10) + int(trail[1], 16) - 0xDC00
            )
        value.append(chr(character))
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
        end = sections[index + 1].body if index + 1 < len(sections) else len(text)
        found = _BUILT_IN_SOURCE.search(text, heading.end, end)
        decoded = found and _decode(text, found.end())
        if decoded:
            yield decoded


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
        while end < len(source) and source[end] in " \t":
            end += 1
        indentation = before[: len(before) - len(before.lstrip())]
        last = source.rfind("\n", start, end)
        for index in range(start, end):
            if source[index] == "\n":
                yield index, "\n" + (indentation if index == last else "")
            else:
                yield index, "\r" if source[index] == "\r" else ""


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
            singleton = "*" if value.startswith("*") else ""
            path = value.removeprefix("*")
            path = paths.get(path, "") if path.startswith("uid://") else path
            if path.startswith("res://") and path.removeprefix("res://") in members:
                result[name] = singleton + path
        return result

    autoloads = held(authored)
    autoloads.update(held(declared))
    return autoloads


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


def _load(
    manifest: dict, execroot: Path, work: Path, root: Path, staged: set[str]
) -> dict[str, list[dict]]:
    """
    Load the unit's files in the staged project; return what Godot reported per file.

    The closure is every staged file: the members and what the import results and the
    interfaces of the closure's other units hold in place of their scripts and assets.
    """
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
    # The runtime configuration enables no editor plugin, the action's included:
    # validate.gd records the result.
    stub = f"res://{ACTION_DIRECTORY}/{_STUB}"
    project = root / "project.godot"
    project.write_text(
        compose_project(
            project.read_text(encoding="utf-8"),
            {},
            {
                name: ("*" if value.startswith("*") else "") + stub
                for name, value in autoloads.items()
            },
            "",
        ),
        encoding="utf-8",
    )
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
        "@rules_godot//godot:tool branch a library for that platform, such as "
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


def validate(manifest: dict, output: Path, execroot: Path) -> None:
    with staged_project(manifest, execroot, "godot-validate-") as (work, root, staged):
        # A file whose tool annotations cannot be removed fails before Godot starts.
        undecodable = remove_tool_mode(root, staged)
        findings = (
            {} if undecodable else _load(manifest, execroot, work, root, set(staged))
        )
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
