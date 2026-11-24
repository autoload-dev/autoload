"""
Find the files each compiled source of a configured engine tree includes, transitively.

Remote and disk cache keys contain every declared input of a compile action, so each
source declares only what it can include. The scan is textual and ignores conditional
compilation: it finds a superset, since an undeclared include fails the action in a
sandbox or on a remote executor.

Generated files do not exist when the graph is rendered. Their includes are the include
directives that the code of their generator writes, as literal paths or as templates.
"""

import os
import re
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import NamedTuple, Protocol, Self

# Includes, imports and __has_include checks, whose answer an undeclared header would
# change, by their delimiter.
_DIRECTIVES = (
    re.compile(
        r'^[ \t]*#[ \t]*(?:include|include_next|import)[ \t]*([<"])([^>"\n]+)[>"]',
        re.MULTILINE,
    ),
    re.compile(r'__has_include(?:_next)?[ \t]*\([ \t]*([<"])([^>"\n]+)[>"]'),
)

# Macros that name a header for a computed include, such as FreeType's FT_FREETYPE_H.
# The file that expands one may be elsewhere, so no directory is preferred.
_HEADER_MACRO = re.compile(
    r'^[ \t]*#[ \t]*define[ \t]+\w+[ \t]+[<"]([^>"\n]+)[>"]', re.MULTILINE
)

# An include directive a generator writes: at the start of a line of a template, or at
# the start of a string. Directives quoted inside messages are none.
_GENERATED_DIRECTIVE = re.compile(
    r"""(?:^|["'])[ \t]*#[ \t]*(?:include|import)[ \t]*[<"]([^>"\n]*)[>"]""", re.MULTILINE
)

# A header that a compiler option names for a computed include, as Mbed TLS's
# -DMBEDTLS_CONFIG_FILE=\"godot_mbedtls_config.h\" does.
_OPTION_HEADER = re.compile(r'^-D\w+=\\?[<"](.+?)\\?[>"]$')
_INCLUDE_OPTIONS = ("-isystem", "-iquote", "-I")
_PLACEHOLDER = re.compile(r"\{[^}]*\}")
_IGNORED_DIRECTORIES = ("_scons", "_bazel_generators")


class Generated(NamedTuple):
    """A generated file: the code of its generator and the files the generator reads."""

    code: str
    inputs: tuple[str, ...]


class CompileGroup(NamedTuple):
    """Sources that compile with the same options and include directories."""

    sources: Sequence[str]
    includes: Sequence[str]
    copts: Sequence[str]


def tree_files(root: Path) -> set[str]:
    """
    Return the files below the source root, relative to it, without the build tools.

    Linked directories count, as they did for the header glob this scan replaces.
    """
    files: set[str] = set()
    for directory, directories, names in os.walk(root, followlinks=True):
        logical = os.path.relpath(directory, root)
        if logical == ".":
            directories[:] = [
                name for name in directories if name not in _IGNORED_DIRECTORIES
            ]
        files.update(os.path.normpath(os.path.join(logical, name)) for name in names)
    return files


def _include_directory(option: str) -> str | None:
    """Return the directory an include option such as -Ithirdparty/zlib names, or None."""
    flag = next((flag for flag in _INCLUDE_OPTIONS if option.startswith(flag)), "")
    return option[len(flag) :] or None if flag else None


def option_includes(copts: Iterable[str]) -> tuple[list[str], list[str]]:
    """Return the include directories and the computed includes that options name."""
    copts = list(copts)
    headers = [
        match.group(1) for option in copts if (match := _OPTION_HEADER.match(option))
    ]
    directories = [name for option in copts if (name := _include_directory(option))]
    return directories, headers


class _Resolver:
    """Resolves an include like a compiler, but to every directory that has the file."""

    def __init__(self, known: Collection[str], directories: Iterable[str]) -> None:
        self.known = known
        self.directories = tuple(dict.fromkeys([*directories, "."]))
        self._templates: dict[str, list[str]] = {}

    def resolve(self, path: str, include: str, quoted: bool = False) -> list[str]:
        """
        Return the files an include of a file may name.

        A quoted include of a file beside the including one finds only that file, as a
        compiler does. Otherwise the file's directory and every include directory of any
        compile group count, which covers include_next and each group the file is
        compiled in.
        """
        beside = self._existing(os.path.dirname(path), include)
        if beside and quoted:
            return [beside]
        found = (self._existing(base, include) for base in self.directories)
        return list(dict.fromkeys(name for name in [beside, *found] if name))

    def template(self, include: str, inputs: Sequence[str]) -> list[str]:
        """
        Return the files a templated include may name, such as "{module}/register_types.h".

        A template without a literal path, such as "{header}", names the generator's inputs.
        """
        parts = _PLACEHOLDER.split(include)
        if not any("/" in part for part in parts):
            return list(inputs)
        if include not in self._templates:
            pattern = re.compile(".+".join(map(re.escape, parts)) + "$")
            self._templates[include] = sorted(
                name for name in self.known if pattern.search(name)
            )
        return self._templates[include]

    def _existing(self, base: str, include: str) -> str | None:
        candidate = os.path.normpath(os.path.join(base, include))
        if candidate.startswith("..") or candidate not in self.known:
            return None
        return candidate


def _directives(text: str) -> Iterator[tuple[str, bool]]:
    """Yield each include of a file's text and whether it is quoted."""
    for pattern in _DIRECTIVES:
        for delimiter, include in pattern.findall(text):
            yield include, delimiter == '"'
    for include in _HEADER_MACRO.findall(text):
        yield include, False


def _file_includes(root: Path, path: str, resolver: _Resolver) -> set[str]:
    try:
        text = (root / path).read_text(errors="replace")
    except FileNotFoundError, IsADirectoryError:
        return set()
    return {
        name
        for include, quoted in _directives(text)
        for name in resolver.resolve(path, include, quoted)
    }


def _generated_includes(path: str, generated: Generated, resolver: _Resolver) -> set[str]:
    found: set[str] = set()
    for include in _GENERATED_DIRECTIVE.findall(generated.code):
        if "{" in include:
            found.update(resolver.template(include, generated.inputs))
        else:
            found.update(resolver.resolve(path, include))
    return found


def include_graph(
    root: Path,
    groups: Iterable[CompileGroup],
    generated: Mapping[str, Generated],
    extra_roots: Iterable[str] = (),
) -> dict[str, frozenset[str]]:
    """
    Return each file that the groups' sources reach mapped to the files it includes.

    A source also includes the headers its options name. Extra roots, such as Swift's
    bridging header, are followed like sources.
    """
    groups = list(groups)
    directories = [
        name
        for group in groups
        for name in [*group.includes, *option_includes(group.copts)[0]]
    ]
    resolver = _Resolver(tree_files(root) | set(generated), directories)
    forced = _option_headers(groups, resolver)
    graph: dict[str, frozenset[str]] = {}
    pending = [*forced, *extra_roots]
    while pending:
        path = pending.pop()
        if path not in graph:
            graph[path] = _includes(root, path, generated, resolver) | forced.get(
                path, set()
            )
            pending.extend(graph[path])
    return graph


def _option_headers(
    groups: Iterable[CompileGroup], resolver: _Resolver
) -> dict[str, set[str]]:
    """Return each source mapped to the headers its group's options name."""
    forced: dict[str, set[str]] = {}
    for group in groups:
        _directories, names = option_includes(group.copts)
        for source in group.sources:
            forced.setdefault(source, set()).update(
                found for name in names for found in resolver.resolve(source, name)
            )
    return forced


def _includes(
    root: Path, path: str, generated: Mapping[str, Generated], resolver: _Resolver
) -> frozenset[str]:
    if path in generated:
        return frozenset(_generated_includes(path, generated[path], resolver))
    return frozenset(_file_includes(root, path, resolver))


def components(graph: Mapping[str, Collection[str]]) -> list[list[str]]:
    """
    Return the strongly connected components of an include graph, dependencies first.

    Header guards let headers include each other; Bazel dependencies cannot form cycles,
    and the files of a cycle are included together anyway.
    """
    return _Components(graph).search()


class _Union(Protocol):
    def __or__(self, other: Self, /) -> Self: ...


def transitive[T: _Union](
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


def reached_directories(
    graph: Mapping[str, Collection[str]], directories: Iterable[str]
) -> dict[str, frozenset[str]]:
    """
    Return each file of an include graph mapped to the directories, as spelled, that hold
    it or a file it includes, transitively, at any depth.

    The scan resolves an include to every directory that has the file, so an include
    directory that holds no file a source reaches resolves none of its includes. The
    source root, ".", holds every file.
    """
    normalized = {directory: str(PurePosixPath(directory)) for directory in directories}
    own: dict[str, frozenset[str]] = {}
    for name in graph:
        ancestors = {str(parent) for parent in PurePosixPath(name).parents}
        own[name] = frozenset(
            directory for directory, path in normalized.items() if path in ancestors
        )
    return transitive(graph, own, frozenset())


class _Components:
    """Tarjan's algorithm, iterative, since include chains outgrow Python's recursion."""

    def __init__(self, graph: Mapping[str, Collection[str]]) -> None:
        self.graph = graph
        self.index: dict[str, int] = {}
        self.low: dict[str, int] = {}
        self.stack: list[str] = []
        self.on_stack: set[str] = set()
        self.result: list[list[str]] = []

    def search(self) -> list[list[str]]:
        for start in sorted(self.graph):
            if start not in self.index:
                self._search_from(start)
        return self.result

    def _search_from(self, start: str) -> None:
        work = [self._enter(start)]
        while work:
            node, edges = work[-1]
            successor = next((name for name in edges if name not in self.index), None)
            if successor is not None:
                work.append(self._enter(successor))
                continue
            work.pop()
            self._leave(node, work[-1][0] if work else None)

    def _enter(self, node: str) -> tuple[str, Iterator[str]]:
        self.index[node] = self.low[node] = len(self.index)
        self.stack.append(node)
        self.on_stack.add(node)
        return node, iter(sorted(self.graph[node]))

    def _leave(self, node: str, parent: str | None) -> None:
        on_stack = [
            self.index[name] for name in self.graph[node] if name in self.on_stack
        ]
        self.low[node] = min([self.low[node], *on_stack])
        if parent is not None:
            self.low[parent] = min(self.low[parent], self.low[node])
        if self.low[node] == self.index[node]:
            self.result.append(self._pop(node))

    def _pop(self, node: str) -> list[str]:
        component: list[str] = []
        while not component or component[-1] != node:
            component.append(self.stack.pop())
            self.on_stack.discard(component[-1])
        return sorted(component)
