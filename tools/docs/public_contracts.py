"""
Public configuration targets and public libraries, compared with their kinds' contracts.

Sections: Public configuration targets, Public libraries.
"""

from collections.abc import Mapping
from typing import Any

from tools.docs.evidence import Evidence
from tools.docs.output_contracts import ConfiguredTarget, has_provider

# ==== Public configuration targets ============================================


# Evaluated providers that identify each public configuration target kind.
_REQUIRED_PROVIDERS = {
    "platform": "PlatformInfo",
    "constraint_setting": "ConstraintSettingInfo",
    "constraint_value": "ConstraintValueInfo",
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
    # Starlark cannot name the providers of these kinds; their rule class identifies them.
    if kind in {"bool_flag", "toolchain_type"}:
        return None
    if kind not in _REQUIRED_PROVIDERS:
        return label + ": unclassified public target kind " + str(kind)
    if _REQUIRED_PROVIDERS[kind] not in providers:
        return label + ": missing " + _REQUIRED_PROVIDERS[kind]
    return None


def check_public_targets(evidence: Evidence, labels: list[str]) -> list[str]:
    """Require public settings, platforms and toolchain types to be metadata-only."""
    observed = evidence.configured({}, labels)
    errors = []
    for label in labels:
        target = observed[label]
        if any((target.files, target.executable, target.runfiles)):
            errors.append(label + ": public configuration target must be metadata-only")
        rule = evidence.loading.elements.get(label)
        kind = rule.attrib["class"] if rule is not None else None
        providers = set(target.providers)
        if error := _kind_error(label, kind, rule, providers):
            errors.append(error)
    return errors


# ==== Public libraries ========================================================


def library_errors(label: str, target: ConfiguredTarget, provider: str) -> list[str]:
    """
    Require a public library to return its consumers' provider.

    A library incompatible with its configuration makes the evidence, and with it the
    contract test, incompatible: Bazel skips that test instead of running it.
    """
    if not has_provider(target, provider):
        return [label + ": public library is missing " + provider]
    return []


def check_public_libraries(evidence: Evidence, libraries: Mapping[str, Any]) -> list[str]:
    """Require each public library, in its configuration, to return its provider."""
    return [
        error
        for label, library in sorted(libraries.items())
        for error in library_errors(
            label,
            evidence.configured(library["settings"], [label])[label],
            library["provider"],
        )
    ]
