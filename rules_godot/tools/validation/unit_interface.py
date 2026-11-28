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
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple

from tools.inputs.mapped_paths import add_root_arguments, resolve_paths, resolver
from tools.inputs.originals import (
    IMPORT_ARCHIVE,
    Original,
    read_original,
    tree_entries,
    write_originals,
)
from tools.resources.class_fragment import skip_arguments
from tools.resources.files import IMPORT, import_base
from tools.resources.text import IMPORTER, REMAP_PATH, Token, lex, remap_section

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


def _nesting(token: Token) -> int:
    """How a token changes the depth of brackets: 1 if it opens one, -1 if it closes one."""
    if token.category != "punctuation":
        return 0
    if token.value in "([{":
        return 1
    return -1 if token.value in ")]}" else 0


def _continues(line: list[Token], depth: int) -> bool:
    """
    Whether a newline after these tokens continues the logical line.

    It does inside brackets and after a backslash, but not after a string that ends in one.
    """
    if depth:
        return True
    return bool(line) and (line[-1].category, line[-1].value) == ("punctuation", "\\")


def _logical_lines(tokens: list[Token]) -> list[list[Token]]:
    """Group tokens into the logical lines GDScript reads indentation from."""
    lines: list[list[Token]] = []
    line: list[Token] = []
    depth = 0
    for token in tokens:
        if token.category != "newline":
            depth = max(depth + _nesting(token), 0)
            line.append(token)
        elif line and not _continues(line, depth):
            lines.append(line)
            line = []
    if line:
        lines.append(line)
    return lines


def _indentation(source: str, line: list[Token]) -> int:
    """The width of the blanks before a logical line's first token."""
    start = source.rfind("\n", 0, line[0].start) + 1
    return line[0].start - start


def _starts_annotation(line: list[Token], index: int) -> bool:
    """Whether line[index] starts an annotation, `@name`."""
    if index + 1 >= len(line):
        return False
    return line[index].value == "@" and line[index + 1].category == "identifier"


def _skip_annotations(line: list[Token], index: int) -> int:
    """The index after the annotations, with their arguments, starting at line[index]."""
    while _starts_annotation(line, index):
        index += 2
        if index < len(line) and line[index].value == "(":
            index = skip_arguments(line, index)
    return index


def _block_colon(line: list[Token], index: int) -> int | None:
    """The index of the first colon outside brackets from line[index], or None."""
    depth = 0
    for position in range(index, len(line)):
        token = line[position]
        if (token.category, token.value) == ("punctuation", ":") and not depth:
            return position
        depth += _nesting(token)
    return None


def _names_await(body: list[Token]) -> bool:
    """Whether `await` stands in the body as part of a node path or member access."""
    return any(
        before.value in _PATH_PUNCTUATION and token.value == "await"
        for before, token in pairwise(body)
    )


def _return_type(signature: list[Token]) -> list[str] | None:
    """The values of a signature's return type tokens; None if it declares none."""
    # The return type follows the parameters. Their defaults may hold lambdas with
    # return types of their own.
    values = [token.value for token in signature]
    after = skip_arguments(signature, values.index("(")) if "(" in values else len(values)
    return values[after + 2 : -1] if values[after : after + 2] == ["-", ">"] else None


def _stub(signature: list[Token], body: list[Token]) -> str | None:
    """
    The statement that replaces a function body, or None to keep the body.

    Args:
        signature: The tokens from `func` to the colon before the body, both included.
        body: The tokens of the body.
    """
    identifiers = {token.value for token in body if token.category == "identifier"}
    awaits = "await" in identifiers
    # An await in a lambda makes the lambda a coroutine, not the function. Telling
    # where the lambda ends would take a parser.
    if awaits and "func" in identifiers:
        return None
    if _names_await(body):
        return None
    returns = _return_type(signature)
    if returns is None or returns == ["void"]:
        return f"await {_VARIANT}" if awaits else "pass"
    return f"return await {_VARIANT}" if awaits else f"return {_VARIANT}"


def _members(
    source: str, lines: list[list[Token]]
) -> Iterator[tuple[list[Token], list[list[Token]]]]:
    """Each member's line in a class body, with the more indented lines of its block."""
    if not lines:
        return
    members = _indentation(source, lines[0])
    index = 0
    while index < len(lines):
        end = index + 1
        while end < len(lines) and _indentation(source, lines[end]) > members:
            end += 1
        yield lines[index], lines[index + 1 : end]
        index = end


def _block_opening(line: list[Token]) -> tuple[int, int] | None:
    """
    The index of a member's keyword, after its annotations and `static`, and of the colon
    that opens its block; None for a member without a block.
    """
    start = _skip_annotations(line, 0)
    if start < len(line) and line[start].value == "static":
        start += 1
    if start >= len(line) or line[start].category != "identifier":
        return None
    colon = _block_colon(line, start)
    return None if colon is None else (start, colon)


def _function_body(
    signature: list[Token], rest: list[Token], block: list[list[Token]]
) -> Iterator[tuple[int, int, str]]:
    """
    The span of a function's body and the statement that replaces it, unless the body stays.

    Args:
        signature: The tokens from `func` to the colon before the body, both included.
        rest: The tokens after the colon on the function's line.
        block: The lines of the function's block.

    Yields:
        The body's start and end offsets and its stub, or nothing.
    """
    body = rest + [token for line in block for token in line]
    if not body:
        return
    statement = _stub(signature, body)
    if statement is not None:
        yield signature[-1].end, body[-1].end, statement


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
    for line, block in _members(source, lines):
        opening = _block_opening(line)
        if opening is None:
            continue
        start, colon = opening
        keyword = line[start].value
        if keyword == "class" and colon + 1 == len(line):
            yield from _function_bodies(source, block)
        elif keyword == "func":
            yield from _function_body(line[start : colon + 1], line[colon + 1 :], block)


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


def _script_file(file: Path) -> Original:
    """A script's interface; a script that is no UTF-8 text is its own."""
    data = file.read_bytes()
    try:
        return script_interface(data.decode("utf-8")).encode("utf-8")
    except UnicodeDecodeError:
        return data


def _without_import_files(assets: dict[str, Path]) -> list[str]:
    """The paths of the assets, without the paths of their .import files."""
    return [
        path
        for path in assets
        if not (path.endswith(IMPORT) and path.removesuffix(IMPORT) in assets)
    ]


def _asset_files(path: str, interface: AssetInterface) -> dict[str, Original]:
    """
    The files that dependents stage for an asset with an interface.

    They are an empty file at its path, its .import file and the stand-in that file names.
    """
    return {
        path: b"",
        path + IMPORT: interface.settings.encode("utf-8"),
        interface.stand_in: interface.content.encode("utf-8"),
    }


def _asset_interfaces(
    assets: dict[str, Path], imported: dict[str, Original]
) -> tuple[dict[str, Original], tuple[str, ...]]:
    """
    The files that dependents stage for a unit's assets.

    Returns:
        The files by resource path, and the import bases of the assets whose imported
        files their stand-ins replace.
    """
    files: dict[str, Original] = {}
    replaced = []
    for path in _without_import_files(assets):
        settings = read_original(imported.get(path + IMPORT, assets[path + IMPORT]))
        interface = asset_interface(path, settings.decode("utf-8", errors="replace"))
        if interface is None:
            files |= {path: assets[path], path + IMPORT: settings}
        else:
            replaced.append(import_base(path))
            files |= _asset_files(path, interface)
    return files, tuple(replaced)


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
    files: dict[str, Original] = {
        path: _script_file(file) for path, file in scripts.items()
    }
    imported = dict(tree_entries(imports))
    asset_files, replaced = _asset_interfaces(assets, imported)
    files |= asset_files
    for relative, original in imported.items():
        if relative not in files and not relative.startswith(replaced):
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
