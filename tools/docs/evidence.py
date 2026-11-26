"""
Evaluated loading and configured facts for the API output-contract checker.

The ruleset's contract tests (godot/tests/api_contracts/contract_test.bzl) give them as
declared inputs: a genquery's XML of the fixtures' loading facts, which names repositories
canonically, and `contract_evidence`'s JSON of their configured facts per configuration.

Sections: Labels, Loading facts, Configured facts.
"""

import json
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from tools.conventions.context import EvidenceError, Location, Target
from tools.docs.output_contracts import ConfiguredTarget

# ==== Labels ==================================================================


def unqualified(label: str) -> str:
    """A label without its repository, as the evidence of one module is keyed."""
    return label.partition("//")[2]


class Labels:
    """
    Name labels as the cases write them, with apparent repositories.

    ``canonical`` maps labels in their apparent form to the canonical one that loading
    facts report; their repositories give the mapping of every other label.
    """

    def __init__(self, canonical: Mapping[str, str]) -> None:
        self.repositories = {
            value.partition("//")[0]: label.partition("//")[0]
            for label, value in canonical.items()
        }
        # The main repository: genquery names its labels without one.
        self.repositories.pop("@@", None)

    def apparent(self, label: str) -> str:
        repository, separator, rest = label.partition("//")
        if separator and repository in self.repositories:
            return self.repositories[repository] + "//" + rest
        return label


# ==== Loading facts ===========================================================


def _location(value: str) -> Location:
    """A ``path:line:column`` value as Bazel reports it, unresolved."""
    path, line, _column = value.rsplit(":", 2)
    return Location(path, int(line))


def _rule(rule: ET.Element, labels: Labels) -> Target:
    """The loading facts of one rule that the checks compare: kind, visibility, flags."""
    strings = {
        item.attrib["name"]: item.attrib.get("value", "")
        for item in rule.findall("string")
    }
    origin = strings.get("generator_location")
    return Target(
        label=labels.apparent(rule.attrib["name"]),
        location=_location(rule.attrib["location"]),
        strings=MappingProxyType(strings),
        booleans=MappingProxyType(
            {
                item.attrib["name"]: item.attrib.get("value") == "true"
                for item in rule.findall("boolean")
            }
        ),
        generator_location=_location(origin) if origin else None,
        kind=rule.attrib["class"],
        labels=MappingProxyType(
            {
                item.attrib["name"]: labels.apparent(item.attrib["value"])
                for item in rule.findall("label")
                if "value" in item.attrib
            }
        ),
        label_lists=MappingProxyType(
            {
                item.attrib["name"]: tuple(
                    labels.apparent(child.attrib["value"]) for child in item
                )
                for item in rule.findall("list")
                if all(child.tag == "label" and "value" in child.attrib for child in item)
            }
        ),
        label_keyed_strings=MappingProxyType({}),
        outputs=(),
        string_lists=MappingProxyType({}),
    )


@dataclass(frozen=True)
class Loading:
    """
    A genquery's loading facts: rules and their XML by apparent label, and the source
    files with public visibility.
    """

    rules: Mapping[str, Target]
    elements: Mapping[str, ET.Element]
    sources: frozenset[str]


def decode_loading(text: str, labels: Labels) -> Loading:
    try:
        query = ET.fromstring(text)
    except ET.ParseError as error:
        raise EvidenceError(f"cannot parse the loading facts: {error}") from error
    rules = {}
    elements = {}
    for element in query.findall("rule"):
        rule = _rule(element, labels)
        rules[rule.label] = rule
        elements[rule.label] = element
    sources = frozenset(
        labels.apparent(source.attrib["name"])
        for source in query.findall("source-file")
        if any(
            item.attrib["name"] == "//visibility:public"
            for item in source.findall("visibility-label")
        )
    )
    return Loading(rules, elements, sources)


def invocation(label: str, targets: Iterable[Target]) -> tuple[Target, ...]:
    """The rules that the authored call of the root ``label`` emits, among loaded targets."""
    targets = tuple(targets)
    roots = [
        target for target in targets if unqualified(target.label) == unqualified(label)
    ]
    if len(roots) != 1:
        raise EvidenceError(f"{label}: unresolved evaluated invocation root")
    return tuple(target for target in targets if target.origin == roots[0].origin)


# ==== Configured facts ========================================================


@dataclass(frozen=True)
class Configuration:
    """The configured facts of one configuration's targets, by their authored labels."""

    settings: Mapping[str, str]
    targets: Mapping[str, ConfiguredTarget]


def decode_configured(text: str) -> Configuration:
    """Decode one `contract_evidence` file."""
    try:
        value = json.loads(text)
        targets = {
            fact["label"]: ConfiguredTarget(
                label=fact["label"],
                files=int(fact["files"]),
                runfiles=int(fact["runfiles"]),
                executable=bool(fact["executable"]),
                providers=frozenset(fact["providers"]),
                groups=frozenset(fact["groups"]),
            )
            for fact in value["facts"]
        }
        settings = dict(value["settings"])
    except (ValueError, KeyError, TypeError) as error:
        raise EvidenceError(f"invalid evaluated configured evidence: {error}") from error
    return Configuration(settings, targets)


@dataclass(frozen=True)
class Evidence:
    """Every fact one contract test reads: loading, configurations and behavior tests."""

    loading: Loading
    configurations: tuple[Configuration, ...]
    tests: frozenset[str] = frozenset()

    def configuration(
        self, settings: Mapping[str, str]
    ) -> Mapping[str, ConfiguredTarget]:
        """The configured facts of every target analyzed with the settings."""
        matches = [
            configuration.targets
            for configuration in self.configurations
            if configuration.settings == dict(settings)
        ]
        if len(matches) != 1:
            raise EvidenceError(f"no configured evidence for settings {dict(settings)}")
        return matches[0]

    def configured(
        self, settings: Mapping[str, str], labels: Iterable[str]
    ) -> dict[str, ConfiguredTarget]:
        """The configured facts of labels in the configuration of the settings."""
        labels = list(labels)
        targets = self.configuration(settings) if labels else {}
        missing = [label for label in labels if label not in targets]
        if missing:
            raise EvidenceError(f"no configured evidence for {', '.join(missing)}")
        return {label: targets[label] for label in labels}
