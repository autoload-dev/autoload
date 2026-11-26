"""The entrypoints of generated repositories, compared with their documented contracts."""

import re
from collections.abc import Mapping

from tools.conventions.context import Target
from tools.docs.evidence import Evidence
from tools.docs.output_contracts import (
    ConfiguredTarget,
    Contract,
    active,
    has_consumer_visibility,
    is_shared_library,
    kind_errors,
)


def _pattern(name: str) -> re.Pattern[str]:
    """Match a documented entrypoint name; each placeholder spans one name segment."""
    parts = re.split(r"(\{[a-z_]+\})", name)
    return re.compile(
        "".join(r"[^/:]+" if part.startswith("{") else re.escape(part) for part in parts)
    )


def _documented_form(label: str) -> str:
    """Replace a label's repository with the documented placeholder."""
    return "@{repository}//" + label.partition("//")[2]


def _reaches_consumers(label: str, visibility: tuple[str, ...]) -> bool:
    """
    Recognize access from outside the generated repository.

    Consumers live in other repositories, so a grant to another package of the same
    repository, such as its toolchain registration, keeps a target internal.
    """
    repository = label.partition("//")[0] + "//"
    outside = tuple(grant for grant in visibility if not grant.startswith(repository))
    return has_consumer_visibility(label, outside)


def repository_errors(
    contract: Contract,
    case: dict,
    rules: Mapping[str, Target],
    sources: set[str],
    observed: Mapping[str, ConfiguredTarget],
) -> list[str]:
    """Compare discovered public repository targets with source and case contracts.

    ``case["entrypoints"]`` maps each documented pattern to its fixture labels.
    """
    errors = []
    if [(row["kind"], row["cardinality"]) for row in contract.defaults] != [
        ("repository", "none")
    ]:
        errors.append("evaluated repository API must declare repository default kind")
    if contract.groups:
        errors.append("repository APIs do not directly expose output groups")
    rows = {row["name"]: row for row in active(contract.companions, case["conditions"])}
    entrypoints = case["entrypoints"]
    for name in sorted(rows.keys() - entrypoints.keys()):
        errors.append("missing repository entrypoint case: " + name)
    for name in sorted(entrypoints.keys() - rows.keys()):
        errors.append("undocumented repository entrypoint: " + name)
    public = {
        label
        for label, target in rules.items()
        if _reaches_consumers(label, target.label_lists.get("visibility", ()))
    }
    expected = {
        label
        for labels in entrypoints.values()
        for label in labels
        if label not in sources
    }
    # A case observes only the rows its conditions make available; targets of an inactive
    # conditional row belong to the cases that enable it.
    inactive = [
        _pattern(row["name"]) for row in contract.companions if row["name"] not in rows
    ]
    for label in sorted(public - expected):
        if any(pattern.fullmatch(_documented_form(label)) for pattern in inactive):
            continue
        errors.append("undocumented public repository rule: " + label)
    for label in sorted(expected - public):
        errors.append("missing public repository target: " + label)
    for name, labels in entrypoints.items():
        if not labels:
            errors.append("missing acquired dataset: " + name)
        row = rows.get(name)
        for label in labels:
            target = observed.get(label)
            if target is None:
                errors.append("missing configured repository entrypoint: " + label)
                continue
            if row is None:
                continue
            rule = rules.get(label)
            errors.extend(
                label + ": " + error
                for error in kind_errors(
                    row["kind"],
                    target,
                    test=rule is not None and rule.is_test,
                    shared_library=rule is not None
                    and is_shared_library(rule.kind, rule.booleans),
                )
            )
            if row["visibility"] != "public":
                errors.append(label + ": repository entrypoints must be public")
            testonly = rule is not None and rule.booleans.get("testonly", False)
            if row["testonly"] != str(testonly).lower():
                errors.append(label + ": source testonly differs from evaluated loading")
    return errors


def check_repository(evidence: Evidence, case: dict, contract: Contract) -> list[str]:
    """
    Compare the public targets of the packages that a case's entrypoints lie in with the
    documented entrypoints, then inspect each of them.

    The loading facts cover the packages of the entrypoints only: a genquery cannot
    enumerate a repository, so a public rule in a package without a documented entrypoint
    escapes this check.
    """
    labels = [label for entries in case["entrypoints"].values() for label in entries]
    repositories = {label.partition("//")[0] for label in labels}
    loading = evidence.loading
    rules = {
        label: rule
        for label, rule in loading.rules.items()
        if label.partition("//")[0] in repositories
    }
    sources = {
        label for label in loading.sources if label.partition("//")[0] in repositories
    }
    known = [label for label in labels if label in rules or label in sources]
    observed = evidence.configured(case["settings"], known)
    return repository_errors(contract, case, rules, sources, observed)
