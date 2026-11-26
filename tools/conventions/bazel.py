"""
The Bazel evidence tool: the loading queries that rules consume, each run once and cached per
module. Decoding the query output is the context's (tools/conventions/context.py).

A module loads in a workspace, a Bazel server: its own directory, or the root module's, which
names it through its repository. Each workspace loads all of its modules in one query.
"""

import json
import threading
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from tools.conventions.context import (
    EvidenceError,
    Fact,
    Module,
    Target,
    query_files,
    query_targets,
    run_tool,
)

Frames = tuple[tuple[str, str], ...]
# The attribute that holds the label, by XML element of a loading query; other attributes,
# such as strings, keep their values.
LABEL_ATTRIBUTES = {
    "rule": "name",
    "source-file": "name",
    "generated-file": "name",
    "rule-input": "name",
    "rule-output": "name",
    "label": "value",
}


def repository(label: str) -> str:
    """The name of the repository a label names, apparent or canonical; empty for the main one."""
    return label.partition("//")[0].lstrip("@").removesuffix("+")


@dataclass(frozen=True)
class Scope:
    """
    Where a module loads: the workspace whose Bazel server queries it, and the repository by
    which that workspace names it, empty where the module is the workspace's own.
    """

    workspace: Path
    repository: str = ""

    def qualify(self, label: str) -> str:
        """Name a label of the module from the workspace."""
        if self.repository and label.startswith("//"):
            return f"@{self.repository}{label}"
        return label

    def localize(self, label: str) -> str:
        """Name a label of the workspace as the module itself does."""
        if self.repository and repository(label) == self.repository:
            return "//" + label.partition("//")[2]
        return label

    def localize_element(self, element: ET.Element) -> ET.Element:
        """Name the labels of an XML query element, and of its children, as the module does."""
        for item in element.iter():
            attribute = LABEL_ATTRIBUTES.get(item.tag)
            if attribute in item.attrib:
                item.attrib[attribute] = self.localize(item.attrib[attribute])
        return element


def evaluated_frames(stack: Iterable[str]) -> Frames:
    """Retain named Starlark call frames supplied by Bazel, without source guessing."""
    result = []
    for frame in stack:
        file, _, _, function = frame.rsplit(":", 3)
        if file.endswith(".bzl") and function.strip() != "<toplevel>":
            result.append((file, function.strip()))
    return tuple(result)


def _parse(output: str) -> ET.Element:
    try:
        return ET.fromstring(output)
    except ET.ParseError as error:
        raise EvidenceError(f"cannot parse Bazel query output: {error}") from error


def _instantiation(line: str) -> tuple[str, list[str]]:
    """The name and the instantiation stack of one rule of a streamed proto query."""
    try:
        value = json.loads(line)["rule"]
        return value["name"], value.get("instantiationStack", [])
    except (ValueError, KeyError) as error:
        raise EvidenceError(
            f"invalid evaluated instantiation evidence: {error}"
        ) from error


class Bazel:
    def __init__(self, root: Path, scopes: Mapping[Module, Scope] | None = None) -> None:
        """
        ``scopes`` says where each module loads, together with the others of its workspace;
        a module without one loads alone in its own directory.
        """
        self.root = root
        self._groups: dict[Path, dict[Module, Scope]] = defaultdict(dict)
        for module, scope in (scopes or {}).items():
            self._groups[scope.workspace][module] = scope
        self._locks: dict[Path, threading.Lock] = defaultdict(threading.Lock)
        self._rules: dict[Module, tuple[Target, ...]] = {}
        self._facts: dict[Module, dict[str, Fact]] = {}
        self._invocations: dict[Module, Mapping[str, Frames]] = {}
        self._dependents: dict[
            tuple[Module, tuple[str, ...], tuple[str, ...]], frozenset[str]
        ] = {}

    def _group(self, module: Module) -> dict[Module, Scope]:
        """The modules that load in the module's workspace, by their scope."""
        for group in self._groups.values():
            if module in group:
                return group
        return {module: Scope(self.root / module.path)}

    def _load[K, V](
        self,
        cache: dict[K, V],
        key: Callable[[Module], K],
        module: Module,
        load: Callable[[dict[Module, Scope]], Mapping[Module, V]],
    ) -> V:
        """
        A module's cached evidence; on a miss, ``load`` queries the module's whole workspace
        once, under the workspace's lock, and caches the result for each of its modules.
        """
        if key(module) not in cache:
            group = self._group(module)
            with self._locks[group[module].workspace]:
                if key(module) not in cache:
                    for member, value in load(group).items():
                        cache[key(member)] = value
        return cache[key(module)]

    @staticmethod
    def _partition[T](
        group: Mapping[Module, Scope], items: Iterable[tuple[str, T]]
    ) -> dict[Module, list[T]]:
        """Group a workspace's query results by the module whose label names them."""
        owners = {scope.repository: module for module, scope in group.items()}
        result: dict[Module, list[T]] = {module: [] for module in group}
        for label, item in items:
            owner = owners.get(repository(label))
            if owner is None:
                raise EvidenceError(f"{label}: no loaded module owns it")
            result[owner].append(item)
        return result

    @staticmethod
    def _patterns(group: Mapping[Module, Scope]) -> str:
        """The rules of each package of the group's modules."""
        patterns = [
            scope.qualify(f"//{package}:all")
            for module, scope in group.items()
            for package in module.packages
        ]
        return "kind(rule, set(" + " ".join(patterns) + "))"

    @staticmethod
    def _run(workspace: Path, expression: str, *options: str) -> str:
        return run_tool(
            ["bazel", "query", expression, *options, "--noshow_progress"], workspace
        )

    def _xml(self, workspace: Path, expression: str) -> ET.Element:
        """Run a loading query for its XML with default attribute values."""
        return _parse(
            self._run(workspace, expression, "--output=xml", "--xml:default_values")
        )

    def dependent_tests(
        self, module: Module, labels: tuple[str, ...], excluded_tags: tuple[str, ...]
    ) -> frozenset[str]:
        """
        The module's tests that depend on one of the labels, in their loading graph. Tests with
        an excluded tag stay out of the graph, so their dependencies are never loaded.
        """

        def load(group: dict[Module, Scope]) -> dict[Module, frozenset[str]]:
            universe = " + ".join(scope.qualify("//...") for scope in group.values())
            tags = "|".join(excluded_tags)
            output = self._run(
                group[module].workspace,
                f"let all = tests({universe}) in let tests = $all except "
                f'attr(tags, "\\b({tags})\\b", $all) in $tests intersect '
                f"rdeps($tests, {' + '.join(labels)})",
                "--output=label",
            )
            found = self._partition(group, ((label, label) for label in output.split()))
            return {
                m: frozenset(map(group[m].localize, items)) for m, items in found.items()
            }

        return self._load(
            self._dependents, lambda m: (m, labels, excluded_tags), module, load
        )

    def invocations(self, module: Module) -> Mapping[str, Frames]:
        """Evaluated source/function frames, including each outermost macro owner."""

        def load(group: dict[Module, Scope]) -> dict[Module, Mapping[str, Frames]]:
            output = self._run(
                group[module].workspace,
                self._patterns(group),
                "--output=streamed_jsonproto",
                "--proto:instantiation_stack",
            )
            rules = map(_instantiation, output.splitlines())
            found = self._partition(
                group, ((name, (name, stack)) for name, stack in rules)
            )
            return {
                m: MappingProxyType(
                    {
                        group[m].localize(name): evaluated_frames(
                            map(group[m].localize, stack)
                        )
                        for name, stack in items
                    }
                )
                for m, items in found.items()
            }

        return self._load(self._invocations, lambda m: m, module, load)

    def rules(self, module: Module) -> tuple[Target, ...]:
        def load(group: dict[Module, Scope]) -> dict[Module, tuple[Target, ...]]:
            query = self._xml(group[module].workspace, self._patterns(group))
            found = self._partition(
                group, ((rule.attrib["name"], rule) for rule in query.findall("rule"))
            )
            result = {}
            for m, items in found.items():
                local = ET.Element("query")
                local.extend(group[m].localize_element(item) for item in items)
                result[m] = query_targets(self.root, m, local)
                self._facts.setdefault(m, {}).update(
                    {target.label: target for target in result[m]}
                )
            return result

        return self._load(self._rules, lambda m: m, module, load)

    def inspect(self, module: Module, labels: tuple[str, ...]) -> Mapping[str, Fact]:
        """Resolve explicit labels, including external repositories, without analysis."""
        scope = self._group(module)[module]
        with self._locks[scope.workspace]:
            cache = self._facts.setdefault(module, {})
            missing = sorted(set(labels) - cache.keys())
            if missing:
                query = scope.localize_element(
                    self._xml(
                        scope.workspace,
                        "set("
                        + " ".join(json.dumps(scope.qualify(label)) for label in missing)
                        + ")",
                    )
                )
                cache.update(
                    {
                        target.label: target
                        for target in query_targets(self.root, module, query)
                    }
                )
                cache.update(query_files(self.root, module, query))
                unresolved = set(missing) - cache.keys()
                if unresolved:
                    raise EvidenceError(
                        "Bazel did not resolve labels: " + ", ".join(sorted(unresolved))
                    )
        return MappingProxyType({label: cache[label] for label in labels})

    def query(self, module: Module, expression: str) -> ET.Element:
        """
        Run a loading query in the module's workspace, naming its labels as the module does;
        the API documentation's checks extend the tool with their own queries (tools/docs).
        """
        scope = self._group(module)[module]
        return scope.localize_element(self._xml(scope.workspace, expression))
