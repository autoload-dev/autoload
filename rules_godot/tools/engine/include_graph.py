"""
Find the files each compiled source of a configured engine tree includes, transitively.

Remote and disk cache keys contain every declared input of a compile action, so each
source declares only what it can include. The scan is textual and ignores conditional
compilation: it finds a superset, since an undeclared include fails the action in a
sandbox or on a remote executor.

Generated files do not exist when the graph is rendered. Their includes are the include
directives that the code of their generator writes, as literal paths or as templates. A
custom module's code comes by label at build time (custom_modules.py), so the scan
cannot read it either: a source that reaches it may include every header, through
ANY_HEADER.

Sections: Inputs, Components, Include resolution.
"""

import os
import re
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from tools.engine.source_tree import HEADER_SUFFIXES, SOURCE_SUFFIXES

# ==== Inputs ==================================================================


# A header that a compiler option names for a computed include, as Mbed TLS's
# -DMBEDTLS_CONFIG_FILE=\"godot_mbedtls_config.h\" does.
_OPTION_HEADER = re.compile(r'^-D\w+=\\?[<"](.+?)\\?[>"]$')

_INCLUDE_OPTIONS = ("-isystem", "-iquote", "-I")

_IGNORED_DIRECTORIES = ("_scons", "_bazel_generators")

# What a source that reaches a custom module's code includes beside it: a file of no tree
# that includes every header of the tree and its generators. A module's code changes
# without the recipe, so those compile actions declare every header rather than what its
# current text includes. Only sources include it, so it closes no cycle of headers.
ANY_HEADER = "_custom_modules/_any_header"


class Generated(NamedTuple):
    """
    A generated file: the code of its generator, the files the generator reads and the
    files it writes.
    """

    code: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]


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


# ==== Components ==============================================================


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


def components(graph: Mapping[str, Collection[str]]) -> list[list[str]]:
    """
    Return the strongly connected components of an include graph, dependencies first.

    Header guards let headers include each other; Bazel dependencies cannot form cycles,
    and the files of a cycle are included together anyway.
    """
    return _Components(graph).search()


def reaching(
    graph: Mapping[str, Collection[str]], matches: Callable[[str], bool]
) -> set[str]:
    """Return the files whose include closure, themselves included, has a matching file."""
    found: set[str] = set()
    for component in components(graph):
        # What a component includes decides before its files are read.
        reaches = any(
            include in found for name in component for include in graph[name]
        ) or any(matches(name) for name in component)
        if reaches:
            found.update(component)
    return found


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
    spellings: dict[str, set[str]] = {}
    for directory in directories:
        spellings.setdefault(str(PurePosixPath(directory)), set()).add(directory)
    reached: dict[str, frozenset[str]] = {}
    # Dependencies come first, and the files of a cycle reach the same directories.
    for component in components(graph):
        found = {
            spelling
            for name in component
            for parent in PurePosixPath(name).parents
            for spelling in spellings.get(str(parent), ())
        }
        for name in component:
            for include in graph[name]:
                found |= reached.get(include, frozenset())
        reached.update(dict.fromkeys(component, frozenset(found)))
    return reached


# ==== Include resolution ======================================================


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

_PLACEHOLDER = re.compile(r"\{[^}]*\}")


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

        A template without a literal path, such as "{header}" or "{target_h}", names one of
        the given files.
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


class TreeCache:
    """
    The files of a source tree and their include directives, read once.

    The runtime variants of a recipe render their graphs from one tree, so they share it.
    code names the custom modules' code files, whose contents come by label at build time:
    the scan reads none of them.
    """

    def __init__(self, root: Path, code: Collection[str] = frozenset()) -> None:
        self.root = root
        self.code = code
        self._files: set[str] | None = None
        self._directives: dict[str, list[tuple[str, bool]]] = {}

    def files(self) -> set[str]:
        if self._files is None:
            self._files = tree_files(self.root)
        return self._files

    def directives(self, path: str) -> list[tuple[str, bool]]:
        if path not in self._directives:
            try:
                text = (self.root / path).read_text(errors="replace")
            except FileNotFoundError, IsADirectoryError:
                text = ""
            self._directives[path] = list(_directives(text))
        return self._directives[path]


def _file_includes(tree: TreeCache, path: str, resolver: _Resolver) -> set[str]:
    return {
        name
        for include, quoted in tree.directives(path)
        for name in resolver.resolve(path, include, quoted)
    }


def _generated_includes(path: str, generated: Generated, resolver: _Resolver) -> set[str]:
    """
    Return the files a generated file may include.

    A template without a literal path names one of the generator's inputs or one of the
    other headers it writes: Godot's translation generators write a header and a source
    that includes it as "{target_h}". Both files have the same code, which cannot tell
    which file a directive belongs to, so the sources stay out.
    """
    named = [
        *generated.inputs,
        *(
            name
            for name in generated.outputs
            if name != path and PurePosixPath(name).suffix not in SOURCE_SUFFIXES
        ),
    ]
    found: set[str] = set()
    for include in _GENERATED_DIRECTIVE.findall(generated.code):
        if "{" in include:
            found.update(resolver.template(include, named))
        else:
            found.update(resolver.resolve(path, include))
    return found


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
    tree: TreeCache, path: str, generated: Mapping[str, Generated], resolver: _Resolver
) -> frozenset[str]:
    if path in generated:
        return frozenset(_generated_includes(path, generated[path], resolver))
    return frozenset(_file_includes(tree, path, resolver))


def _any_include(name: str) -> bool:
    """Whether a module's code may include a file: any header, and any file of a module."""
    return name != ANY_HEADER and (
        name.endswith(HEADER_SUFFIXES)
        or name.startswith(ANY_HEADER.partition("/")[0] + "/")
    )


class _Scan(NamedTuple):
    """
    What the scan of one graph reads: the tree and its generated files.

    roots are the graph's sources, which ANY_HEADER leaves out, so it closes no cycle.
    """

    tree: TreeCache
    generated: Mapping[str, Generated]
    resolver: _Resolver
    roots: frozenset[str]

    def includes(self, path: str) -> frozenset[str]:
        if path == ANY_HEADER:
            return frozenset(
                name
                for name in self.resolver.known
                if _any_include(name) and name not in self.roots
            )
        if path in self.tree.code:
            return frozenset()
        return _includes(self.tree, path, self.generated, self.resolver)

    def follow(
        self,
        graph: dict[str, frozenset[str]],
        pending: list[str],
        forced: Mapping[str, Collection[str]],
    ) -> None:
        """Add the files pending reach to the graph, with what each includes."""
        while pending:
            path = pending.pop()
            if path not in graph:
                graph[path] = self.includes(path) | forced.get(path, set())
                pending.extend(graph[path])


def include_graph(
    source: Path | TreeCache,
    groups: Iterable[CompileGroup],
    generated: Mapping[str, Generated],
    extra_roots: Iterable[str] = (),
) -> dict[str, frozenset[str]]:
    """
    Return each file that the groups' sources reach mapped to the files it includes.

    A source also includes the headers its options name. Extra roots, such as Swift's
    bridging header, are followed like sources. source is the tree's root, or a TreeCache
    that shares the files the scan reads between graphs of one tree. The includes of the
    tree's custom module code are unknown: a source or root that reaches it includes
    ANY_HEADER.
    """
    tree = source if isinstance(source, TreeCache) else TreeCache(source)
    groups = list(groups)
    directories = [
        name
        for group in groups
        for name in [*group.includes, *option_includes(group.copts)[0]]
    ]
    resolver = _Resolver(tree.files() | set(generated), directories)
    forced = _option_headers(groups, resolver)
    roots = [*forced, *extra_roots]
    scan = _Scan(tree, generated, resolver, frozenset(roots))
    graph: dict[str, frozenset[str]] = {}
    scan.follow(graph, list(roots), forced)
    if tree.code:
        found = reaching(graph, lambda name: name in tree.code)
        for root in found.intersection(roots):
            graph[root] |= {ANY_HEADER}
        scan.follow(graph, [ANY_HEADER] if found else [], forced)
    return graph
