"""
The Bazel evidence tool: the loading queries of one module that rules consume, each run once
and cached per module. Decoding the query output is the context's (tools/conventions/context.py).
"""

import json
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
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


def evaluated_frames(stack: Iterable[str]) -> tuple[tuple[str, str], ...]:
    """Retain named Starlark call frames supplied by Bazel, without source guessing."""
    result = []
    for frame in stack:
        file, _, _, function = frame.rsplit(":", 3)
        if file.endswith(".bzl") and function.strip() != "<toplevel>":
            result.append((file, function.strip()))
    return tuple(result)


class Bazel:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._rules: dict[Module, tuple[Target, ...]] = {}
        self._facts: dict[Module, dict[str, Fact]] = {}
        self._invocations: dict[Module, Mapping[str, tuple[tuple[str, str], ...]]] = {}

    def query(self, module: Module, expression: str) -> ET.Element:
        """Run a loading query and return its XML with default attribute values."""
        output = run_tool(
            [
                "bazel",
                "query",
                expression,
                "--output=xml",
                "--xml:default_values",
                "--noshow_progress",
            ],
            self.root / module.path,
        )
        try:
            return ET.fromstring(output)
        except ET.ParseError as error:
            raise EvidenceError(f"cannot parse Bazel query output: {error}") from error

    def labels(self, module: Module, expression: str) -> frozenset[str]:
        """The labels a loading query names."""
        output = run_tool(
            ["bazel", "query", expression, "--output=label", "--noshow_progress"],
            self.root / module.path,
        )
        return frozenset(output.split())

    def dependent_tests(
        self, module: Module, labels: tuple[str, ...], excluded_tags: tuple[str, ...]
    ) -> frozenset[str]:
        """
        The module's tests that depend on one of the labels, in their loading graph. Tests with
        an excluded tag stay out of the graph, so their dependencies are never loaded.
        """
        targets = " + ".join(labels)
        tags = "|".join(excluded_tags)
        return self.labels(
            module,
            f'let all = tests(//...) in let tests = $all except attr(tags, "\\b({tags})\\b", $all)'
            f" in $tests intersect rdeps($tests, {targets})",
        )

    def invocations(self, module: Module) -> Mapping[str, tuple[tuple[str, str], ...]]:
        """Evaluated source/function frames, including each outermost macro owner."""
        if module not in self._invocations:
            patterns = ["//" + package + ":all" for package in module.packages]
            output = run_tool(
                [
                    "bazel",
                    "query",
                    "kind(rule, set(" + " ".join(patterns) + "))",
                    "--output=streamed_jsonproto",
                    "--proto:instantiation_stack",
                    "--noshow_progress",
                ],
                self.root / module.path,
            )
            result = {}
            for line in output.splitlines():
                try:
                    value = json.loads(line)["rule"]
                    result[value["name"]] = evaluated_frames(
                        value.get("instantiationStack", [])
                    )
                except (ValueError, KeyError) as error:
                    raise EvidenceError(
                        f"invalid evaluated instantiation evidence: {error}"
                    ) from error
            self._invocations[module] = MappingProxyType(result)
        return self._invocations[module]

    def rules(self, module: Module) -> tuple[Target, ...]:
        if module in self._rules:
            return self._rules[module]
        patterns = ["//" + package + ":all" for package in module.packages]
        query = self.query(module, "kind(rule, set(" + " ".join(patterns) + "))")
        self._rules[module] = query_targets(self.root, module, query)
        self._facts.setdefault(module, {}).update(
            {target.label: target for target in self._rules[module]}
        )
        return self._rules[module]

    def inspect(self, module: Module, labels: tuple[str, ...]) -> Mapping[str, Fact]:
        """Resolve explicit labels, including external repositories, without analysis."""
        cache = self._facts.setdefault(module, {})
        missing = sorted(set(labels) - cache.keys())
        if missing:
            query = self.query(
                module, "set(" + " ".join(json.dumps(label) for label in missing) + ")"
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
