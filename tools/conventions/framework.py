"""Run independent convention rules and collect uniform, source-located diagnostics."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol

from tools.conventions.context import RULESET_MODULE, Context, Location

# The catalogue that documents every rule, by its ID as anchor.
CATALOGUE = (RULESET_MODULE / "docs/public/conventions.md").as_posix()


@dataclass(frozen=True)
class RuleInfo:
    id: str
    title: str

    @property
    def documentation(self) -> str:
        return f"{CATALOGUE}#{self.id.lower()}"


@dataclass(frozen=True)
class Finding:
    location: Location
    message: str
    status: Literal["violation", "not_checked"] = "violation"
    required: bool = False


class Rule(Protocol):
    info: RuleInfo

    def evaluate(self, context: Context) -> Iterable[Finding]: ...


@dataclass(frozen=True)
class Diagnostic:
    rule: RuleInfo
    finding: Finding

    def __str__(self) -> str:
        location = self.finding.location
        status = " not checked" if self.finding.status == "not_checked" else ""
        return (
            f"{location.path}:{location.line}: {self.rule.id}{status}: "
            f"{self.finding.message} ({self.rule.documentation})"
        )


@dataclass(frozen=True)
class Report:
    diagnostics: tuple[Diagnostic, ...]

    @property
    def violations(self) -> tuple[Diagnostic, ...]:
        return tuple(
            item for item in self.diagnostics if item.finding.status == "violation"
        )

    @property
    def failures(self) -> tuple[Diagnostic, ...]:
        """Violations plus incomplete evidence explicitly required by its owner."""
        return tuple(
            item
            for item in self.diagnostics
            if item.finding.status == "violation" or item.finding.required
        )

    @property
    def not_checked(self) -> tuple[Diagnostic, ...]:
        return tuple(
            item for item in self.diagnostics if item.finding.status == "not_checked"
        )


def run(context: Context, rules: Iterable[Rule]) -> Report:
    """Give each rule the same snapshot; never reinterpret its policy or applicability."""
    rules = tuple(rules)
    ids = [rule.info.id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("Convention rule IDs must be unique")
    diagnostics = [
        Diagnostic(rule.info, finding)
        for rule in rules
        for finding in rule.evaluate(context)
    ]
    # A repeated finding is a rule defect; hiding it would mask wrong applicability.
    duplicates = [str(item) for item, count in Counter(diagnostics).items() if count > 1]
    if duplicates:
        raise ValueError(
            "Duplicate convention findings: " + "; ".join(sorted(duplicates))
        )
    return Report(
        tuple(
            sorted(
                diagnostics,
                key=lambda item: (
                    item.finding.location.path,
                    item.finding.location.line,
                    item.rule.id,
                    item.finding.status,
                    item.finding.message,
                ),
            )
        )
    )
