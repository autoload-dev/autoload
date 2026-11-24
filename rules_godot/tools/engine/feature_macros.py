"""
Find the feature macros that each compiled source of a configured engine tree can read.

Every -D option is part of a compile action's key in the remote and disk cache, so a
feature macro that a whole compile group defines makes flipping that feature rebuild
every source of the group. A source can keep only the feature macros that a file it
reaches can read. A dropped macro that its preprocessor reads would compile silently
into a different object, so the scan keeps a macro whenever it cannot rule out a read:

- Only Godot's feature macros are dropped: names that end in _ENABLED or _DISABLED and
  that are not reserved for the implementation, which __ or _ and a capital letter start.
  The scan does not see system headers; none reads such a name.
- A file reads a macro whose name is one of its words, in code, strings or comments,
  or a word of the value of one of the source's -D options.
- Token pasting assembles names from fragments: the literal operands of ##, the
  arguments of macros that paste their parameters, and the words those expand to. A
  macro is kept when its name can be assembled from the fragments the source reaches,
  with numbers, which __LINE__ and __COUNTER__ supply.
- A generated file does not exist when the graph is rendered. Its words are those of
  its generator's code, data and text inputs, without case, and so are its fragments.
"""

import io
import re
import tokenize
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

try:
    from .include_graph import Generated, components
except ImportError:
    from include_graph import Generated, components

FEATURE_MACRO = re.compile(r"(?!__|_[A-Z])\w+_(?:ENABLED|DISABLED)")

_DEFINE_OPTION = re.compile(r"-D(\w+)(?:=(.*))?$", re.DOTALL)
_WORD = re.compile(r"\w+")
_SPLICE = re.compile(r"\\\r?\n")
_DEFINE = re.compile(
    r"^[ \t]*#[ \t]*define[ \t]+(\w+)(?:\(([^)\n]*)\))?(.*)$", re.MULTILINE
)
_INVOCATION = re.compile(r"\b(\w+)\s*\(")
_PASTE = re.compile(r"(\w*)\s*##\s*(\w*)")
_STRING_TOKENS = {
    tokenize.STRING,
    tokenize.FSTRING_MIDDLE,
    getattr(tokenize, "TSTRING_MIDDLE", tokenize.FSTRING_MIDDLE),
}


class _Define(NamedTuple):
    """
    A macro definition: its name, the words of its body, the operands of its ## and its
    parameters, with __VA_ARGS__, which an object-like macro has none of.
    """

    name: str
    words: frozenset[str]
    operands: frozenset[str]
    parameters: frozenset[str]

    def pastes_parameter(self) -> bool:
        return not self.parameters.isdisjoint(self.operands)

    def forwards(self, pasting: Collection[str]) -> bool:
        """Return whether the body can pass a parameter to one of the pasting macros."""
        return not self.parameters.isdisjoint(self.words) and not self.words.isdisjoint(
            pasting
        )


class _Reads(NamedTuple):
    """What a file, or every file a source reaches, can read or paste of the names."""

    names: frozenset[str]
    fragments: frozenset[str]
    folded: frozenset[str]

    def __or__(self, other: _Reads) -> _Reads:
        return _Reads(
            self.names | other.names,
            self.fragments | other.fragments,
            self.folded | other.folded,
        )


_NOTHING = _Reads(frozenset(), frozenset(), frozenset())


def feature_options(copts: Iterable[str]) -> dict[str, str]:
    """Return each -D option of a Godot feature macro mapped to the macro's name."""
    return {
        option: match.group(1)
        for option in copts
        if (match := _DEFINE_OPTION.match(option))
        and FEATURE_MACRO.fullmatch(match.group(1))
    }


def _option_words(copts: Iterable[str]) -> set[str]:
    """Return the words of the values that -D options give their macros."""
    return {
        word
        for option in copts
        if (match := _DEFINE_OPTION.match(option)) and match.group(2)
        for word in _WORD.findall(match.group(2))
    }


def _substrings(name: str) -> Iterator[str]:
    return (
        name[start:end]
        for start in range(len(name))
        for end in range(start + 1, len(name) + 1)
    )


def assembles(name: str, fragments: Collection[str], folded: Collection[str]) -> bool:
    """
    Return whether pasting fragments can form a name.

    Numbers are fragments, and folded fragments match without case.
    """
    reachable = [True] + [False] * len(name)
    for end in range(1, len(name) + 1):
        reachable[end] = any(
            reachable[start] and _is_fragment(name[start:end], fragments, folded)
            for start in range(end)
        )
    return reachable[-1]


def _is_fragment(piece: str, fragments: Collection[str], folded: Collection[str]) -> bool:
    return piece.isdigit() or piece in fragments or piece.casefold() in folded


def _read_text(path: Path) -> str:
    try:
        return _SPLICE.sub("", path.read_text(errors="replace"))
    except FileNotFoundError, IsADirectoryError:
        return ""


def _defines(text: str) -> Iterator[_Define]:
    for match in _DEFINE.finditer(text):
        parameters = match.group(2)
        body = match.group(3)
        yield _Define(
            match.group(1),
            frozenset(_WORD.findall(body)),
            frozenset(
                operand for pair in _PASTE.findall(body) for operand in pair if operand
            ),
            frozenset()
            if parameters is None
            else frozenset(
                [
                    "__VA_ARGS__",
                    *(name.strip().removesuffix("...") for name in parameters.split(",")),
                ]
            ),
        )


def _transitive[T: (frozenset[str], _Reads)](
    graph: Mapping[str, Collection[str]], own: Mapping[str, T], empty: T
) -> dict[str, T]:
    """Return each node of a graph mapped to the union of its value and its successors'."""
    result: dict[str, T] = {}
    for component in components(graph):
        value = empty
        for node in component:
            value = value | own.get(node, empty)
            for successor in graph[node]:
                value = value | result.get(successor, empty)
        result.update(dict.fromkeys(component, value))
    return result


def _arguments(text: str, opening: int) -> str:
    """Return the text between a parenthesis and the one that closes it."""
    depth = 0
    for index in range(opening, len(text)):
        depth += {"(": 1, ")": -1}.get(text[index], 0)
        if depth == 0:
            return text[opening + 1 : index]
    return text[opening + 1 :]


class _Macros:
    """
    The macro definitions of every scanned file.

    A macro pastes when its body pastes one of its parameters, or passes one to a macro
    that pastes. Definitions of one name in different files count together.
    """

    def __init__(self, texts: Iterable[str]) -> None:
        self.definitions = [define for text in texts for define in _defines(text)]
        self.pasting = {
            define.name for define in self.definitions if define.pastes_parameter()
        }
        while forwarding := {
            define.name
            for define in self.definitions
            if define.name not in self.pasting and define.forwards(self.pasting)
        }:
            self.pasting |= forwarding

    def pasted_words(self, text: str) -> set[str]:
        """Return the literal operands of ## and the arguments of pasting macros."""
        words = {operand for define in _defines(text) for operand in define.operands}
        for match in _INVOCATION.finditer(text):
            if match.group(1) in self.pasting:
                words.update(_WORD.findall(_arguments(text, match.end() - 1)))
        return words

    def expansions(self, relevant: Collection[str]) -> dict[str, frozenset[str]]:
        """Return each macro mapped to the relevant words its expansion can contain."""
        bodies: dict[str, set[str]] = {}
        for define in self.definitions:
            bodies.setdefault(define.name, set()).update(define.words)
        calls = {name: words & bodies.keys() for name, words in bodies.items()}
        own = {
            name: frozenset(words.intersection(relevant))
            for name, words in bodies.items()
        }
        return _transitive(calls, own, frozenset())


class FeatureMacroScan:
    """Decides which feature options each source of an include graph is compiled with."""

    def __init__(
        self,
        root: Path,
        graph: Mapping[str, Collection[str]],
        generated: Mapping[str, Generated],
        copts: Iterable[Sequence[str]],
    ) -> None:
        self.names = frozenset(
            name for options in copts for name in feature_options(options).values()
        )
        self.pieces = frozenset(
            piece for name in self.names for piece in _substrings(name)
        )
        self.folded_pieces = frozenset(piece.casefold() for piece in self.pieces)
        files = self._file_reads(root, graph, generated) if self.names else {}
        self.reads = self._closures(graph, files)

    def copts(self, source: str, copts: Sequence[str]) -> list[str]:
        """Return a source's options without the feature macros it cannot read."""
        options = feature_options(copts)
        if not options:
            return list(copts)
        words = _option_words(copts)
        reads = self.reads.get(source, _NOTHING) | self._reads(words, words)
        kept = {
            name
            for name in options.values()
            if name in reads.names or assembles(name, reads.fragments, reads.folded)
        }
        return [
            option for option in copts if option not in options or options[option] in kept
        ]

    def _reads(
        self,
        words: Iterable[str],
        fragments: Iterable[str],
        folded_words: Iterable[str] = (),
        folded_fragments: Iterable[str] = (),
    ) -> _Reads:
        """
        Return what words and fragments read of the names; folded ones match without case.
        """
        folded = {word.casefold() for word in folded_words}
        return _Reads(
            self.names.intersection(words)
            | frozenset(name for name in self.names if name.casefold() in folded),
            self.pieces.intersection(fragments),
            self.folded_pieces.intersection(word.casefold() for word in folded_fragments),
        )

    def _file_reads(
        self,
        root: Path,
        graph: Mapping[str, Collection[str]],
        generated: Mapping[str, Generated],
    ) -> dict[str, _Reads]:
        texts = {path: _read_text(root / path) for path in graph if path not in generated}
        macros = _Macros(texts.values())
        expansions = macros.expansions(self.pieces)
        reads = {
            path: self._source_reads(text, macros, expansions)
            for path, text in texts.items()
        }
        for path in graph:
            if path in generated:
                words, fragments = _generator_words(root, path, generated)
                reads[path] = self._reads((), (), words, fragments)
        return reads

    def _source_reads(
        self, text: str, macros: _Macros, expansions: Mapping[str, frozenset[str]]
    ) -> _Reads:
        pasted = macros.pasted_words(text)
        fragments = pasted.union(
            *(expansions[word] for word in pasted if word in expansions)
        )
        return self._reads(_WORD.findall(text), fragments)

    def _closures(
        self, graph: Mapping[str, Collection[str]], files: Mapping[str, _Reads]
    ) -> dict[str, _Reads]:
        """Return each file mapped to what it and every file it includes can read."""
        return _transitive(graph, files, _NOTHING)


def _generator_words(
    root: Path,
    path: str,
    generated: Mapping[str, Generated],
    seen: frozenset[str] = frozenset(),
) -> tuple[set[str], set[str]]:
    """
    Return the words a generated file can contain and the fragments it can join.

    A generator joins the text of its code's strings with values: words of its code, data
    and text inputs. A binary input is embedded as numbers. A single character joins
    names only as text of a string, such as the _ of f"{module}_{name}".
    """
    generator = generated[path]
    seen |= {path}
    words = set(_WORD.findall(generator.code + generator.data))
    fragments = _string_words(generator.code)
    for name in generator.inputs:
        if name in generated and name not in seen:
            words |= _generator_words(root, name, generated, seen)[0]
        elif name not in generated:
            words.update(_WORD.findall(_text_input(root / name)))
    fragments.update(word for word in words if len(word) > 1)
    return words, fragments


def _string_words(code: str) -> set[str]:
    """Return the words of a Python file's strings, or of all its code if it does not parse."""
    try:
        strings = [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(code).readline)
            if token.type in _STRING_TOKENS
        ]
    except tokenize.TokenError, SyntaxError:
        strings = [code]
    return {word for string in strings for word in _WORD.findall(string)}


def _text_input(path: Path) -> str:
    """Return a generator input's text, or nothing for a binary file."""
    try:
        return path.read_bytes().decode()
    except FileNotFoundError, IsADirectoryError, UnicodeDecodeError:
        return ""
