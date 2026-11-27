"""
The interface of one unit: what the validations of its dependents read from its files.

When Godot's GDScript analyzer checks a script, it resolves the scripts the script uses only
up to their interface (GDScriptParserRef::INTERFACE_SOLVED): their headers, signals, enums,
constants, variables with the types their initializers give them, inner classes and
function signatures. It never resolves their function bodies; the one fact it takes from a
body is whether the parser found an `await` in it, which makes the function a coroutine.
Godot compiles those scripts afterwards, so their interface must compile, but nothing else
of their compilation reaches the script being checked. Of an imported asset, a loading scene
or script reads only that it exists, its UID and the class of the resource its import
produced; never the converted data.

The interface carries exactly that, so a change to a function body or to an asset's content
yields the same interface and Bazel reruns no dependent validation:

- A script keeps every line but the bodies of its functions and those of its inner classes.
  Each body becomes one statement that compiles under every return type and keeps a
  coroutine a coroutine. A body whose coroutine-ness the tokens do not decide, such as one
  with an `await` and a lambda, stays as it is.
- An imported asset whose import result Godot's own importers wrote becomes an empty file,
  its `.import` file keeps only the remap, now naming a text resource of the same class with
  no data. An asset of another importer, which may give its resource a script, keeps its
  file, its `.import` file and its imported files as they are.

Every other file of the unit, such as a scene, a resource or a script that is no UTF-8 text,
is its own interface and dependents stage it as it is.

Sections: Script interface, Asset interface.
"""

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

from tools.class_fragment import skip_arguments
from tools.godot_files import IMPORT, import_base
from tools.godot_staging import (
    IMPORT_ARCHIVE,
    Original,
    read_original,
    tree_entries,
    write_originals,
)
from tools.mapped_paths import add_root_arguments, resolve_paths, resolver
from tools.resource_text import IMPORTER, REMAP_PATH, Token, lex, remap_section

# The class of the resource each of Godot's own importers produces, which a stand-in has: a
# preloaded resource types its constant by its class. Other importers, such as an add-on's,
# may give their resource a script, so their assets are their own interface.
IMPORTED_CLASSES = {
    "font_data_dynamic": "FontFile",
    "oggvorbisstr": "AudioStreamOggVorbis",
    "scene": "PackedScene",
    "texture": "CompressedTexture2D",
    "wav": "AudioStreamWAV",
    "wavefront_obj": "ArrayMesh",
}


# ==== Script interface ========================================================


# A value of type Variant that is no constant, so the analyzer neither folds it nor rejects
# it for any declared return type, in static and in instance functions alike.
_VARIANT = 'Engine.get_meta(&"")'

# The warnings a script can report only once its function bodies are gone. A dependent's
# validation ignores its dependencies' warnings, but a project may raise one to an error,
# which would fail the interface's compilation and with it the dependent's.
_BODY_WARNINGS = ("unused_parameter", "unused_private_class_variable", "unused_signal")

_IGNORE_BODY_WARNINGS = (
    "@warning_ignore_start("
    + ", ".join(f'"{warning}"' for warning in _BODY_WARNINGS)
    + ")\n"
)

# The tokens after which an identifier is part of a node path or member access, not a
# keyword.
_PATH_PUNCTUATION = ("$", "%", "/", ".")


def _logical_lines(tokens: list[Token]) -> list[list[Token]]:
    """
    Group tokens into the logical lines GDScript reads indentation from.

    A newline ends a line unless it is inside brackets or follows a backslash.
    """
    lines: list[list[Token]] = []
    line: list[Token] = []
    depth = 0
    for token in tokens:
        if token.category == "newline":
            if depth or (line and line[-1].value == "\\"):
                continue
            if line:
                lines.append(line)
            line = []
            continue
        if token.category == "punctuation" and token.value in "([{":
            depth += 1
        elif token.category == "punctuation" and token.value in ")]}":
            depth = max(depth - 1, 0)
        line.append(token)
    if line:
        lines.append(line)
    return lines


def _indentation(source: str, line: list[Token]) -> int:
    """The width of the blanks before a logical line's first token."""
    start = source.rfind("\n", 0, line[0].start) + 1
    return line[0].start - start


def _skip_annotations(line: list[Token], index: int) -> int:
    """The index after the annotations, with their arguments, starting at line[index]."""
    while (
        index + 1 < len(line)
        and line[index].value == "@"
        and line[index + 1].category == "identifier"
    ):
        index += 2
        if index < len(line) and line[index].value == "(":
            index = skip_arguments(line, index)
    return index


def _block_colon(line: list[Token], index: int) -> int | None:
    """The index of the first colon outside brackets from line[index], or None."""
    depth = 0
    for position in range(index, len(line)):
        value = line[position].value
        if line[position].category != "punctuation":
            continue
        if value in "([{":
            depth += 1
        elif value in ")]}":
            depth -= 1
        elif value == ":" and not depth:
            return position
    return None


def _stub(signature: list[Token], body: list[Token]) -> str | None:
    """
    The statement that replaces a function body, or None to keep the body.

    Args:
        signature: The tokens from `func` to the colon before the body, both included.
        body: The tokens of the body.
    """
    identifiers = {token.value for token in body if token.category == "identifier"}
    awaits = "await" in identifiers
    # A lambda's await makes the lambda a coroutine, not the function; telling the lambda's
    # extent apart would take a parser.
    if awaits and "func" in identifiers:
        return None
    for index, token in enumerate(body):
        if (
            token.value == "await"
            and index
            and body[index - 1].value in _PATH_PUNCTUATION
        ):
            return None
    # The return type follows the parameters, whose defaults may hold lambdas with their own.
    values = [token.value for token in signature]
    after = skip_arguments(signature, values.index("(")) if "(" in values else len(values)
    returns = values[after + 2 : -1] if values[after : after + 2] == ["-", ">"] else None
    if returns is None or returns == ["void"]:
        return f"await {_VARIANT}" if awaits else "pass"
    return f"return await {_VARIANT}" if awaits else f"return {_VARIANT}"


def _function_bodies(
    source: str, lines: list[list[Token]]
) -> Iterator[tuple[int, int, str]]:
    """
    The spans of the function bodies of a class body and its inner classes.

    Args:
        source: The script's source.
        lines: The logical lines of the class body.

    Yields:
        Each body's start and end offsets and the statement that replaces it.
    """
    if not lines:
        return
    members = _indentation(source, lines[0])
    index = 0
    while index < len(lines):
        line = lines[index]
        block_end = index + 1
        while block_end < len(lines) and _indentation(source, lines[block_end]) > members:
            block_end += 1
        block = lines[index + 1 : block_end]
        index = block_end
        start = _skip_annotations(line, 0)
        if start < len(line) and line[start].value == "static":
            start += 1
        if start >= len(line) or line[start].category != "identifier":
            continue
        keyword = line[start].value
        colon = _block_colon(line, start)
        if keyword == "class" and colon is not None and colon + 1 == len(line):
            yield from _function_bodies(source, block)
        elif keyword == "func" and colon is not None:
            body = line[colon + 1 :] + [token for each in block for token in each]
            if not body:
                continue
            statement = _stub(line[start : colon + 1], body)
            if statement is not None:
                yield line[colon].end, body[-1].end, statement


def script_interface(source: str) -> str:
    """
    The interface of a GDScript source: the source without its function bodies.

    Args:
        source: The script's source.

    Returns:
        The source with each function body replaced by one statement on the function's
        line, which compiles and is a coroutine exactly when the body was; the source as
        it is when it has no body to replace.
    """
    tokens = lex(source)
    # A restored warning would report again in the stubs below it.
    if any(token.value == "warning_ignore_restore" for token in tokens):
        return source
    spans = list(_function_bodies(source, _logical_lines(tokens)))
    if not spans:
        return source
    # Godot reads a byte order mark only where the file starts.
    bom = "\ufeff" if source.startswith("\ufeff") else ""
    pieces, last = [bom, _IGNORE_BODY_WARNINGS], len(bom)
    for start, end, statement in spans:
        pieces += [source[last:start], " ", statement]
        last = end
    return "".join(pieces) + source[last:]


# ==== Asset interface =========================================================


class AssetInterface(NamedTuple):
    """What dependents stage for an imported asset besides an empty file at its path."""

    # The .import file's text.
    settings: str
    # The resource path of the stand-in the remap names, and its text.
    stand_in: str
    content: str


def asset_interface(path: str, text: str) -> AssetInterface | None:
    """
    The interface of an imported asset, from the .import file its import result holds.

    Args:
        path: The asset's resource path, without res://.
        text: The text of its .import file.

    Returns:
        The interface; None for an asset that is its own interface: one of another
        importer or one without a remapped resource.
    """
    remap = remap_section(text)
    if remap is None or not REMAP_PATH.search(remap):
        return None
    importer = IMPORTER.search(remap)
    kind = importer and IMPORTED_CLASSES.get(importer[1])
    if not kind:
        return None
    # Named as Godot names the asset's imported files, so it is unique in every closure.
    stand_in = import_base(path) + "interface"
    if kind == "PackedScene":
        # Godot loads a text PackedScene only as a scene, which needs a root node; loading
        # instantiates none.
        stand_in += ".tscn"
        content = '[gd_scene format=3]\n\n[node name="Imported" type="Node"]\n'
    else:
        stand_in += ".tres"
        content = f'[gd_resource type="{kind}" format=3]\n\n[resource]\n'
    kept = "".join(
        line for line in remap.splitlines(keepends=True) if not REMAP_PATH.match(line)
    )
    settings = kept.rstrip("\n") + f'\npath="res://{stand_in}"\n'
    return AssetInterface(settings, stand_in, content)


def interface_files(
    scripts: dict[str, Path], assets: dict[str, Path], imports: Path
) -> dict[str, Original]:
    """
    The files of a unit's interface, by resource path.

    Args:
        scripts: The unit's own GDScript files.
        assets: The unit's own files that have an .import file among the unit's files,
            with those .import files.
        imports: The unit's import result.

    Returns:
        Each script's interface, and the import result with each asset of Godot's own
        importers replaced by its interface: an empty file, its .import file's interface
        and the stand-in that replaces the files its import wrote. An asset of another
        importer keeps its file and its import result.
    """
    files: dict[str, Original] = {}
    for path, file in scripts.items():
        data = file.read_bytes()
        try:
            files[path] = script_interface(data.decode("utf-8")).encode("utf-8")
        except UnicodeDecodeError:
            files[path] = data
    imported = dict(tree_entries(imports))
    replaced = []
    for path, file in assets.items():
        if path.endswith(IMPORT) and path.removesuffix(IMPORT) in assets:
            continue
        settings = read_original(imported.get(path + IMPORT, assets[path + IMPORT]))
        interface = asset_interface(path, settings.decode("utf-8", errors="replace"))
        if interface is None:
            files[path] = file
            files[path + IMPORT] = settings
            continue
        replaced.append(import_base(path))
        files[path] = b""
        files[path + IMPORT] = interface.settings.encode("utf-8")
        files[interface.stand_in] = interface.content.encode("utf-8")
    for relative, original in imported.items():
        if relative not in files and not relative.startswith(tuple(replaced)):
            files[relative] = original
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--import", dest="imports", type=Path, required=True)
    add_root_arguments(parser)
    args = parser.parse_args()
    resolve = resolver(args.roots)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))

    def files(key: str) -> dict[str, Path]:
        return {
            path: Path(file)
            for path, file in resolve_paths(manifest[key], resolve).items()
        }

    write_originals(
        interface_files(files("scripts"), files("assets"), args.imports),
        args.output / IMPORT_ARCHIVE,
    )


if __name__ == "__main__":
    main()
