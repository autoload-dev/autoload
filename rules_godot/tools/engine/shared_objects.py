"""
Describe a recipe's generators, header sets and objects for its shared tree repository.

Prototype. Remote and disk cache keys contain every path of a compile action, and a
recipe repository's paths contain its name, so two recipes never share an action. A
tree repository holds one patched source tree for every recipe of a row; each recipe
describes its work there with names that digest everything an action reads, so the
equivalent work of two recipes is one target with one action.

A generated file lies below `_gen/<digest>/` in the tree repository, where the digest
covers its generator's specification and the identity of everything the generator reads.
Work that reads the recipe's revision stays in the recipe repository.
"""

import hashlib
import json
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

try:
    from .include_graph import components
except ImportError:
    from include_graph import components

# Where a recipe's build profile lies in its repository; the tree holds profiles by digest.
_PROFILE = "_build_profile.gdbuild"
# Files only the recipe repository has: its revision's hash and time stamp. The build
# name file depends on the build name alone, so the tree holds it per build name.
_BUILD_NAME = "_revision/build.txt"
_LOCAL_PREFIXES = ("_revision/",)
_DIGEST_LENGTH = 16


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _module_directory(path: str) -> str:
    """The custom module directory of a path, such as _custom_modules/probe/; else empty."""
    parts = path.split("/")
    return "/".join(parts[:2]) + "/" if parts[0] == "_custom_modules" else ""


def generator_python_files(python_files: Iterable[str], code_file: str) -> list[str]:
    """
    The Python files a shared generator reads: the tree's, and its own custom module's.

    Other custom modules' files would make a generator's digest depend on which modules
    the recipe adds.
    """
    own = _module_directory(code_file)
    return sorted(
        path
        for path in python_files
        if not path.startswith("_custom_modules/") or (own and path.startswith(own))
    )


class TreePaths:
    """The identity and tree-repository path of each file a recipe's actions read."""

    def __init__(
        self,
        root: Path,
        generators: Sequence[tuple[Mapping[str, Any], Collection[str]]],
        python_files: Collection[str],
        build_name: str,
    ) -> None:
        self.root = root
        self.build_name = build_name
        self.generators = generators
        self.python_files = python_files
        self.writer = {
            target: index
            for index, (spec, _) in enumerate(generators)
            for target in spec["targets"]
        }
        self._files: dict[str, str] = {}
        self._generators: dict[int, str | None] = {}

    def generator_inputs(self, index: int) -> list[str]:
        """The logical files a shared generator reads."""
        spec, dependencies = self.generators[index]
        python = generator_python_files(self.python_files, spec["code_file"])
        return sorted({*dependencies, *python, spec["code_file"]})

    def generator_digest(self, index: int) -> str | None:
        """The digest of a generator's work; None when it reads a recipe's own file."""
        if index not in self._generators:
            self._generators[index] = None
            identities = [
                (name, self.identity(name)) for name in self.generator_inputs(index)
            ]
            if all(identity for _, identity in identities):
                spec = self.generators[index][0]
                self._generators[index] = _digest({"spec": spec, "inputs": identities})
        return self._generators[index]

    def identity(self, logical: str) -> str | None:
        """What a file contains, as a digest; None for a recipe's own file."""
        if logical == _BUILD_NAME:
            return "build_name:" + self.build_name
        if logical.startswith(_LOCAL_PREFIXES):
            return None
        if logical in self.writer:
            digest = self.generator_digest(self.writer[logical])
            return digest and digest + ":" + logical
        return self._file_digest(logical)

    def path(self, logical: str) -> str | None:
        """Where a file lies in the tree repository; None for a recipe's own file."""
        if logical in self.writer:
            digest = self.generator_digest(self.writer[logical])
            return digest and f"_gen/{digest[:_DIGEST_LENGTH]}/{logical}"
        if logical == _PROFILE:
            return f"_build_profiles/{self._file_digest(logical)}.gdbuild"
        if logical == _BUILD_NAME:
            return f"{build_name_directory(self.build_name)}/build.txt"
        return None if logical.startswith(_LOCAL_PREFIXES) else logical

    def generated_directory(self, logical: str) -> str | None:
        """The `_gen/<digest>` directory of a generated file; None for other files."""
        path = self.path(logical) if logical in self.writer else None
        return path and path[: -len(logical) - 1]

    def _file_digest(self, logical: str) -> str:
        if logical not in self._files:
            self._files[logical] = hashlib.sha256(
                (self.root / logical).read_bytes()
            ).hexdigest()
        return self._files[logical]


def build_name_directory(build_name: str) -> str:
    """Where the tree holds the build name file of a build name."""
    return f"_build_names/{build_name}"


def shared_build_name(paths: TreePaths) -> dict[str, str]:
    """The tree-repository revision whose build name file the recipe's generators read."""
    return {"name": "_b_" + paths.build_name, "build_name": paths.build_name}


def shared_generators(paths: TreePaths) -> list[dict[str, Any]]:
    """The tree-repository generators of every generator that reads no recipe file."""
    result = []
    for index, (spec, _) in enumerate(paths.generators):
        digest = paths.generator_digest(index)
        if not digest:
            continue
        inputs = {
            ":" + str(paths.path(name)): name for name in paths.generator_inputs(index)
        }
        result.append(
            {
                "name": "_g_" + digest[:_DIGEST_LENGTH],
                "spec_json": json.dumps(spec, sort_keys=True),
                "inputs": inputs,
                "outs": [paths.path(target) for target in spec["targets"]],
                "logical_outputs": list(spec["targets"]),
            }
        )
    return result


def _component_deps(
    graph: Mapping[str, Collection[str]],
    component: Iterable[str],
    targets: Mapping[str, str],
) -> list[str] | None:
    """The header sets a component's files include; None when one is a recipe's own."""
    included = {include for file in component for include in graph[file]} - set(component)
    if not included.issubset(targets):
        return None
    return sorted({targets[include] for include in included})


def shared_headers(
    paths: TreePaths, graph: Mapping[str, Collection[str]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """
    Return a header set per set of files that include each other, and each file's set.

    A set that holds or reaches a recipe's own file stays in the recipe repository.
    """
    included = {name for names in graph.values() for name in names}
    result: list[dict[str, Any]] = []
    targets: dict[str, str] = {}
    for component in components(graph):
        if included.isdisjoint(component):
            continue
        hdrs = [paths.path(name) for name in component]
        deps = _component_deps(graph, component, targets)
        if None in hdrs or deps is None:
            continue
        labels = sorted(":" + str(path) for path in hdrs)
        name = "_h_" + _digest({"hdrs": labels, "deps": deps})[:_DIGEST_LENGTH]
        result.append({"name": name, "hdrs": labels, "deps": [":" + dep for dep in deps]})
        targets.update((file, name) for file in component)
    return result, targets


def _closure(graph: Mapping[str, Collection[str]], source: str) -> set[str]:
    seen = {source}
    pending = [source]
    while pending:
        for name in graph.get(pending.pop(), ()):
            if name not in seen:
                seen.add(name)
                pending.append(name)
    return seen


def used_includes(closure: Collection[str], includes: Sequence[str]) -> list[str]:
    """
    The include directories below which a file of the closure lies, in their order.

    The include scan resolves an include to every directory that has the file, so a
    directory without a file of the closure resolves none of the closure's includes.
    """
    return [
        directory
        for directory in includes
        if any(_below(name, directory) for name in closure)
    ]


def _below(name: str, directory: str) -> bool:
    return directory == "." or name.startswith(directory.rstrip("/") + "/")


def generated_includes(
    paths: TreePaths, closure: Iterable[str], includes: Sequence[str]
) -> list[str]:
    """
    The include directories of a source's generated files in the tree repository.

    A generated file found below an include directory of the recipe is found below
    the same directory of its `_gen/<digest>` directory.
    """
    found = [
        (directory, name)
        for name in sorted(closure)
        if (directory := paths.generated_directory(name))
    ]
    directories = (
        directory if base == "." else f"{directory}/{base}"
        for directory, name in found
        for base in [".", *includes]
        if _below(name, base)
    )
    return list(dict.fromkeys(directories))


class Recipe(NamedTuple):
    """What rendering knows of a recipe's compiles."""

    paths: TreePaths
    # Each compile group's language, options, include directories and sources.
    compiled: Sequence[tuple[str, Sequence[str], Sequence[str], Sequence[str]]]
    # What each file includes.
    graph: Mapping[str, Collection[str]]
    # The local defines of each source that has any.
    defines: Mapping[str, Sequence[str]]


def shared_object(
    recipe: Recipe,
    headers: Mapping[str, str],
    group: tuple[str, Sequence[str], Sequence[str]],
    source: str,
) -> dict[str, Any] | None:
    """A source's library in the tree repository; None when it reads a recipe's file."""
    language, copts, includes = group
    paths, graph = recipe.paths, recipe.graph
    closure = _closure(graph, source)
    if any(name not in headers for name in graph[source]) or not all(
        paths.path(name) for name in closure
    ):
        return None
    used = used_includes(closure, includes)
    attributes = {
        "rule": "objc_library" if language == "objc" else "cc_library",
        "srcs": [":" + str(paths.path(source))],
        "copts": list(copts),
        "includes": [*used, *generated_includes(paths, closure, used)],
        "local_defines": list(recipe.defines.get(source, ())),
        "deps": [":_root", *sorted({":" + headers[name] for name in graph[source]})],
    }
    name = "_o_" + source.replace("/", "__") + "_" + _digest(attributes)[:12]
    return {"name": name, **attributes}


def share(tree: str, recipe: Recipe, labels: Sequence[str]) -> list[str]:
    """
    Write the recipe's description for its tree repository and return the engine's
    object labels, given in compile group order, with the shared ones in the tree.
    """
    headers, targets = shared_headers(recipe.paths, recipe.graph)
    objects = []
    result = []
    sources = [
        ((language, copts, includes), source)
        for language, copts, includes, members in recipe.compiled
        for source in members
    ]
    for (group, source), label in zip(sources, labels, strict=True):
        shared = shared_object(recipe, targets, group, source)
        if shared:
            objects.append(shared)
        result.append(f"@{tree}//:{shared['name']}" if shared else label)
    description = {
        "build_names": [shared_build_name(recipe.paths)],
        "generators": shared_generators(recipe.paths),
        "headers": headers,
        "objects": objects,
    }
    (recipe.paths.root / "shared.bzl").write_text(
        "# Generated from Godot SCons; do not edit.\n"
        f"SHARED = {json.dumps(description, indent=1, sort_keys=True)}\n"
    )
    return result
