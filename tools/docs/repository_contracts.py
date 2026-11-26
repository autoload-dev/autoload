"""
Generated-repository entrypoints, public configuration targets and public libraries.

Sections: Repository entrypoints, Public configuration targets, Public libraries.
"""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.conventions.context import Module, Target
from tools.docs.evidence import RULESET_MODULE, EvaluatedBazel, is_test
from tools.docs.output_contracts import (
    CONTRACT_LANES,
    ConfiguredTarget,
    Contract,
    active,
    has_consumer_visibility,
    has_provider,
    is_shared_library,
    kind_errors,
    provider_identity,
)

# ==== Repository entrypoints ==================================================


def _pattern(name: str) -> re.Pattern[str]:
    """Match a documented entrypoint name; each placeholder spans one name segment."""
    parts = re.split(r"(\{[a-z_]+\})", name)
    return re.compile(
        "".join(r"[^/:]+" if part.startswith("{") else re.escape(part) for part in parts)
    )


def _unqualified(label: str) -> str:
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
        if any(pattern.fullmatch(_unqualified(label)) for pattern in inactive):
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
                    test=rule is not None and is_test(rule),
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


def toolchain_bound(labels: list[str], rules: Mapping[str, Target]) -> list[str]:
    """
    Labels that a toolchain with execution constraints in the same repository implements.

    Query reports a toolchain's implementation in canonical form, so the
    implementation is matched by its repository-relative label.
    """
    implementations = {
        (label.partition("//")[0], target.labels["toolchain"].partition("//")[2])
        for label, target in rules.items()
        if target.kind == "toolchain"
        and "toolchain" in target.labels
        and target.label_lists.get("exec_compatible_with")
    }
    return [
        label
        for label in labels
        if (label.partition("//")[0], label.partition("//")[2]) in implementations
    ]


def check_repository(
    bazel: EvaluatedBazel,
    case: dict,
    contract: Contract,
) -> list[str]:
    """Discover generated public targets, then inspect each documented entrypoint."""
    module = Module(Path(case["module"]), ())
    labels = [label for entries in case["entrypoints"].values() for label in entries]
    datasets = case.get("datasets", {})
    repositories = {label.partition("//")[0] for label in labels} | {
        prefix.partition("//")[0] for prefix in datasets.values()
    }
    rules, sources = bazel.repository(
        module,
        " + ".join(
            [f"kind(rule, {repository}//...)" for repository in sorted(repositories)]
            + ["set(" + " ".join(labels) + ")"]
            + [prefix.partition("//")[0] + "//:*" for prefix in datasets.values()]
        ),
    )
    case = dict(case, entrypoints=dict(case["entrypoints"]))
    for name, prefix in datasets.items():
        case["entrypoints"][name] = [
            label for label in sorted(sources) if label.startswith(prefix)
        ]
    known = [
        label
        for entries in case["entrypoints"].values()
        for label in entries
        if label in rules or label in sources
    ]
    # Toolchain resolution gives a toolchain's implementation an execution platform that its
    # toolchain declares, which is this host; configured on its own, the implementation would
    # take the first execution platform, possibly a remote one that cannot run it.
    bound = toolchain_bound(known, rules)
    observed = bazel.configured(
        module, [label for label in known if label not in bound], case["options"]
    )
    if bound:
        observed |= bazel.configured(
            module, bound, [*case["options"], "--config=host-execution"]
        )
    return repository_errors(contract, case, rules, sources, observed)


# ==== Public configuration targets ============================================


# Evaluated providers that identify each public configuration target kind.
_REQUIRED_PROVIDERS = {
    "platform": "PlatformInfo",
    "constraint_setting": "ConstraintSettingInfo",
    "constraint_value": "ConstraintValueInfo",
    "toolchain_type": "ToolchainTypeInfo",
    **{
        kind: "//godot/private:flags.bzl%FlagInfo" for kind in ("string_flag", "int_flag")
    },
}
_PREDICATES = {"values", "define_values", "flag_values", "constraint_values"}


def _kind_error(
    label: str, kind: str | None, rule: Any, providers: set[str]
) -> str | None:
    """The violation of a public configuration target's kind contract, if any."""
    if kind == "config_setting":
        # Bazel does not expose ConfigMatchingProvider to cquery; require an
        # evaluated predicate instead.
        if any(item.attrib.get("name") in _PREDICATES and len(item) for item in rule):
            return None
        return label + ": config_setting has no evaluated predicate"
    if kind == "bool_flag":
        return None
    if kind not in _REQUIRED_PROVIDERS:
        return label + ": unclassified public target kind " + str(kind)
    if _REQUIRED_PROVIDERS[kind] not in providers:
        return label + ": missing " + _REQUIRED_PROVIDERS[kind]
    return None


def check_public_targets(bazel: EvaluatedBazel, labels: list[str]) -> list[str]:
    """Require public settings, platforms and toolchain types to be metadata-only."""
    query = bazel.query(RULESET_MODULE, "set(" + " ".join(labels) + ")")
    rules = {
        element.attrib["name"].partition("//")[2]: element
        for element in query.findall("rule")
    }
    observed = bazel.configured(RULESET_MODULE, labels)
    errors = []
    for label in labels:
        target = observed[label]
        if any((target.files, target.executable, target.runfiles)):
            errors.append(label + ": public configuration target must be metadata-only")
        rule = rules.get(label.partition("//")[2])
        kind = rule.attrib["class"] if rule is not None else None
        providers = {provider_identity(key) for key in target.providers}
        if error := _kind_error(label, kind, rule, providers):
            errors.append(error)
    return errors


# ==== Public libraries ========================================================


def library_errors(label: str, target: ConfiguredTarget, provider: str) -> list[str]:
    """Require a public library to be compatible and to return its consumers' provider."""
    if has_provider(target, "IncompatiblePlatformProvider"):
        return [label + ": public library is incompatible with its lane's configuration"]
    if not has_provider(target, provider):
        return [label + ": public library is missing " + provider]
    return []


def library_lane_errors(libraries: Mapping[str, Any]) -> list[str]:
    """Reject public libraries whose lane no contract check runs, which would go unchecked."""
    return [
        f"{label}: public library names no contract lane: {library['lane']}"
        for label, library in sorted(libraries.items())
        if library["lane"] not in CONTRACT_LANES
    ]


def _library_groups(
    libraries: Mapping[str, Any], lane: str
) -> dict[tuple[str, ...], list[str]]:
    """The public libraries of one lane, by the options of their configuration."""
    groups: dict[tuple[str, ...], list[str]] = {}
    for label, library in sorted(libraries.items()):
        if library["lane"] == lane:
            groups.setdefault(tuple(library["options"]), []).append(label)
    return groups


def check_public_libraries(
    bazel: EvaluatedBazel, libraries: Mapping[str, Any], lane: str
) -> list[str]:
    """Analyze the public libraries of one lane, with one cquery per configuration."""
    errors = []
    for options, labels in _library_groups(libraries, lane).items():
        observed = bazel.configured(RULESET_MODULE, labels, options)
        errors.extend(
            error
            for label in labels
            for error in library_errors(
                label, observed[label], libraries[label]["provider"]
            )
        )
    return errors
