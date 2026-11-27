"""Reusable repository and tool fixtures for convention regressions."""

import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import NotRequired, TypedDict

from tools.addons.modules import ROOT
from tools.addons.new import generate
from tools.conventions.context import (
    Buildozer,
    Call,
    Context,
    EvidenceError,
    Fact,
    GeneratedFile,
    Module,
    SourceFile,
    Target,
    Workspace,
    query_targets,
)
from tools.conventions.framework import Rule


class StaticTools:
    """Serve fixed Starlark and Bazel facts and count each tool's requests."""

    def __init__(
        self, root: Path, calls: tuple[Call, ...], targets: tuple[Target, ...]
    ) -> None:
        self._root = root
        self._calls = calls
        self._targets = targets
        self.owners: dict[str, tuple[tuple[str, str], ...]] = {}
        self.call_requests = 0
        self.rule_requests = 0
        self.facts: dict[str, Fact] = {target.label: target for target in targets}
        # The tests that depend on the labels a rule asks for.
        self.dependents: frozenset[str] = frozenset()

    def calls(self, module: Module) -> tuple[Call, ...]:
        self.call_requests += 1
        return self._calls

    def invocations(self, module: Module) -> Mapping[str, tuple[tuple[str, str], ...]]:
        return self.owners

    def module_name(self, module: Module) -> str:
        """Name each module after its directory; the root module is "main"."""
        return module.path.name or "main"

    def rules(self, module: Module) -> tuple[Target, ...]:
        """Return the targets declared in the module's own BUILD files."""
        self.rule_requests += 1
        builds = {build.as_posix() for build in module.builds}
        return tuple(target for target in self._targets if target.location.path in builds)

    def dependent_tests(
        self, module: Module, labels: tuple[str, ...], excluded_tags: tuple[str, ...]
    ) -> frozenset[str]:
        return self.dependents

    def inspect(self, module: Module, labels: tuple[str, ...]) -> Mapping[str, Fact]:
        missing = set(labels) - self.facts.keys()
        if missing:
            raise EvidenceError("No static facts for: " + ", ".join(sorted(missing)))
        return MappingProxyType({label: self.facts[label] for label in labels})


class Record(TypedDict):
    """One `bazel query --output=xml` rule; each test states the attributes it needs."""

    name: str
    path: str
    line: NotRequired[int]
    strings: NotRequired[dict[str, str]]
    booleans: NotRequired[dict[str, bool]]
    kind: NotRequired[str]
    labels: NotRequired[dict[str, str]]
    label_lists: NotRequired[dict[str, list[str]]]
    string_lists: NotRequired[dict[str, list[str]]]
    label_keyed_strings: NotRequired[dict[str, dict[str, str]]]
    outputs: NotRequired[list[str]]
    owner: NotRequired[str]


def lists(rule: ET.Element, element: str, values: dict[str, list[str]]) -> None:
    """Write list attributes whose elements are all of one type, such as labels."""
    for name, items in values.items():
        group = ET.SubElement(rule, "list", {"name": name})
        for value in items:
            ET.SubElement(group, element, {"value": value})


def query_xml(root: Path, records: list[Record]) -> ET.Element:
    query = ET.Element("query")
    for record in records:
        rule = ET.SubElement(
            query,
            "rule",
            {
                "name": record["name"],
                "location": f"{root / record['path']}:{record.get('line', 1)}:1",
                "class": record.get("kind", "filegroup"),
            },
        )
        for name, value in record.get("strings", {}).items():
            ET.SubElement(rule, "string", {"name": name, "value": value})
        for name, flag in record.get("booleans", {}).items():
            ET.SubElement(rule, "boolean", {"name": name, "value": str(flag).lower()})
        for name, value in record.get("labels", {}).items():
            ET.SubElement(rule, "label", {"name": name, "value": value})
        lists(rule, "label", record.get("label_lists", {}))
        lists(rule, "string", record.get("string_lists", {}))
        for name, values in record.get("label_keyed_strings", {}).items():
            group = ET.SubElement(rule, "dict", {"name": name})
            for label, value in values.items():
                pair = ET.SubElement(group, "pair")
                ET.SubElement(pair, "label", {"value": label})
                ET.SubElement(pair, "string", {"value": value})
        for label in record.get("outputs", []):
            ET.SubElement(rule, "rule-output", {"name": label})
    return query


class RepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        # Every written file; the default workspace inventory.
        self.files: set[str] = set()
        # The root module, which includes the add-on generator's declarations.
        self.write("MODULE.bazel", 'include("//:addons.MODULE.bazel")\n')
        self.write("BUILD.bazel", "")

    def write_consumer_modules(self) -> None:
        """
        Make rules_godot/ the ruleset's module, as in the repository, whose root module holds
        the consumers examples/ and e2e/rules_godot/.
        """
        self.write("rules_godot/MODULE.bazel", "")

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.files.add(name)

    def workspace(self, files: tuple[str, ...] | None = None) -> Workspace:
        return Workspace(self.root, tuple(sorted(self.files)) if files is None else files)

    def file_context(self, files: tuple[str, ...]) -> Context:
        """
        A context over some files, as the file lint gives a rule the changed ones: without
        Bazel evidence and without the modules of the other files.
        """
        self.tools = StaticTools(self.root, (), ())
        return Context(self.workspace(files), self.tools, self.tools)

    def context(
        self,
        calls: tuple[Call, ...] = (),
        records: list[Record] | None = None,
        files: tuple[str, ...] | None = None,
        sources: Mapping[str, str] | None = None,
        generated: tuple[str, ...] = (),
    ) -> Context:
        """Build a context over static facts; `self.tools` counts its tool requests."""
        workspace = self.workspace(files)
        targets = query_targets(
            self.root, workspace.modules[0], query_xml(self.root, records or [])
        )
        self.tools = StaticTools(self.root, calls, targets)
        for record in records or []:
            if "owner" in record:
                file, function = record["owner"].split("%", 1)
                self.tools.owners[record["name"]] = ((file, function),)
            elif record.get("strings", {}).get("generator_function"):
                self.tools.owners[record["name"]] = (
                    ("fixture.bzl", record["strings"]["generator_function"]),
                )
        self.tools.facts.update(
            {
                label: SourceFile(label, (self.root / name).resolve())
                for label, name in (sources or {}).items()
            }
        )
        self.tools.facts.update({label: GeneratedFile(label) for label in generated})
        return Context(workspace, self.tools, self.tools)


class AddonModuleTest(RepositoryTest):
    """
    A repository with what the add-on generator starts from, whose modules are written as the
    generator writes them. A rule's findings read the BUILD files with the real Buildozer
    when the test has one: its path in the variable BUILDOZER (BUILD.bazel).
    """

    rule: Rule

    def setUp(self) -> None:
        super().setUp()
        for name in (".bazelversion", ".bcr/rules_godot/metadata.template.json"):
            self.write(name, (ROOT / name).read_text())

    def module(self, directory: str, addon: str | None = None) -> None:
        """A module as the generator writes it, in the workspace inventory."""
        for path in generate(directory, addon, root=self.root):
            self.files.add(path.relative_to(self.root).as_posix())

    def findings(self, rule: Rule | None = None) -> list[tuple[str, str]]:
        """The findings of the rule, the test's own unless given, by status and message."""
        static = self.context()
        buildozer = os.environ.get("BUILDOZER")
        starlark = (
            Buildozer(self.root, Path(buildozer).resolve())
            if buildozer
            else static.starlark
        )
        context = Context(static.workspace, starlark, static.bazel)
        return [
            (item.status, item.message) for item in (rule or self.rule).evaluate(context)
        ]

    def messages(self, rule: Rule | None = None) -> list[str]:
        return [message for _, message in self.findings(rule)]
