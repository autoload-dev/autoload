"""Compare evaluated public source contracts with configured, evaluated Bazel fixtures."""

import argparse
import json
import os
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.conventions.context import EvidenceError, Module, Target
from tools.docs.api_docs import read_inventory
from tools.docs.coverage import ModuleInfo, module_apis
from tools.docs.evidence import EvaluatedBazel, behavior_tests, is_test, unqualified
from tools.docs.output_contracts import (
    CONTRACT_LANES,
    DEFAULT_CONTRACT_LANE,
    Api,
    ConfiguredTarget,
    active,
    behavior_lane,
    compare,
    coverage_errors,
    has_consumer_visibility,
    is_shared_library,
    kind_errors,
)
from tools.docs.repository_contracts import check_public_targets, check_repository
from tools.docs.ruleset import INVENTORY
from tools.setup.modules import RULESET

MANIFEST = "//godot/tests/api_contracts:case_manifest.json"


def inventory_target(module: str) -> str:
    """The unfiltered evaluated extraction of one public API module."""
    page = module.removeprefix("//").replace("/", "_").replace(":", "_")
    return "//tools/docs/api:" + page.removesuffix(".bzl") + "_inventory.textproto"


def extracted_apis(
    modules: Mapping[str, ModuleInfo],
) -> tuple[dict[str, Api], list[str]]:
    """Index each module's exports by ``module%name``."""
    apis = {}
    errors = []
    for label, module in modules.items():
        entries, problems = module_apis(module)
        apis.update({label + "%" + name: api for name, api in entries.items()})
        errors.extend(f"{label}%{problem}" for problem in problems)
    return apis, errors


def host_case(case: dict[str, Any]) -> dict[str, Any]:
    """Apply the case's host substitutions and defaults."""
    replacements = case.get("host_replacements", {}).get(sys.platform, {})

    def replace(value: Any) -> Any:
        if isinstance(value, str):
            for old, new in replacements.items():
                value = value.replace(old, new)
            return value
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, dict):
            return {replace(key): replace(item) for key, item in value.items()}
        return value

    defaults = {
        "lane": DEFAULT_CONTRACT_LANE,
        "module": ".",
        "options": [],
        "conditions": [],
    }
    return replace({**defaults, **case})


def companion_errors(
    row: dict[str, str], loaded: Target, root: Target, target: ConfiguredTarget
) -> list[str]:
    """Compare one documented companion with its loading and configured facts."""
    errors = kind_errors(
        row["kind"],
        target,
        test=is_test(loaded),
        shared_library=is_shared_library(loaded.kind, loaded.booleans),
    )
    expected = (
        root.label_lists.get("visibility", ())
        if row["visibility"] == "caller"
        else ("//visibility:public",)
    )
    if loaded.label_lists.get("visibility", ()) != expected:
        errors.append("visibility differs from source contract")
    testonly = loaded.booleans.get("testonly", False)
    if row["testonly"] == "inherit":
        if testonly != root.booleans.get("testonly", False):
            errors.append("does not inherit root testonly")
    elif testonly != (row["testonly"] == "true"):
        errors.append("testonly differs from source contract")
    if row["kind"] == "alias" and loaded.kind != "alias":
        errors.append("is not its documented evaluated alias")
    return errors


@dataclass(frozen=True)
class Fixture:
    """
    A target case's loading facts: the rules of its root's invocation by unqualified
    label, its documented companions by label, and rows that resolve to none.
    """

    loaded: Mapping[str, Target]
    companions: Mapping[str, dict[str, str]]
    unresolved: tuple[str, ...]


def fixture(case: dict[str, Any], api: Api, expansion: Iterable[Target]) -> Fixture:
    """Resolve a case's documented companions against its root's invocation."""
    loaded = {unqualified(target.label): target for target in expansion}
    package, _, root = case["target"].rpartition(":")
    unresolved = []
    companions = {}
    for row in active(api.contract.companions, case["conditions"]):
        pattern = row["name"]
        companion = package + ":" + pattern.replace("{name}", root, 1)
        if not pattern.startswith("{name}") or "{" in companion:
            unresolved.append(f"unresolved generated companion pattern {pattern}")
        elif unqualified(companion) not in loaded:
            unresolved.append(f"missing evaluated loading facts for {companion}")
        else:
            companions[companion] = row
    return Fixture(loaded, companions, tuple(unresolved))


def discovered_companions(root: str, api: Api, loaded: Mapping[str, Target]) -> set[str]:
    """Consumer-visible rules of the invocation besides its root, as name patterns."""
    return {
        "{name}" + name.removeprefix(root) if name.startswith(root) else name
        for target in loaded.values()
        if (name := target.label.rpartition(":")[2]) != root
        and has_consumer_visibility(
            target.label,
            target.label_lists.get("visibility", ()),
            symbolic_macro=api.kind == "macro_info",
        )
    }


def check_case(
    case: dict[str, Any],
    api: Api,
    facts: Fixture,
    observed: Mapping[str, ConfiguredTarget],
) -> list[str]:
    """Compare one source contract with its configured fixture and its expansion."""
    label = case["target"]
    root_fact = facts.loaded[unqualified(label)]
    errors = list(facts.unresolved)
    for companion, row in facts.companions.items():
        errors.extend(
            f"companion {companion} {error}"
            for error in companion_errors(
                row, facts.loaded[unqualified(companion)], root_fact, observed[companion]
            )
        )
    errors.extend(
        compare(
            api.contract,
            observed[label],
            test=is_test(root_fact),
            shared_library=is_shared_library(root_fact.kind, root_fact.booleans),
            companions=discovered_companions(label.rpartition(":")[2], api, facts.loaded),
            conditions=case["conditions"],
            forwarded_groups=case.get("forwarded_groups", False),
        )
    )
    return errors


# Contract cases with their extracted API, by case key.
Cases = Mapping[str, tuple[dict[str, Any], Api]]


def case_groups(cases: Cases) -> list[tuple[Module, tuple[str, ...], list[str]]]:
    """
    Case keys grouped by module and options, the host's default options last.

    Options change Bazel's configuration, which discards the module's analysis
    cache; ending on the default configuration leaves it for the next build.
    """
    groups: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for key, (case, _) in sorted(cases.items()):
        groups.setdefault((case["module"], tuple(case["options"])), []).append(key)
    return [
        (Module(Path(module), ()), options, groups[module, options])
        for module, options in sorted(groups, key=lambda group: (not group[1], group))
    ]


def check_targets(
    bazel: EvaluatedBazel, module: Module, options: tuple[str, ...], cases: Cases
) -> dict[str, list[str]]:
    """Check target cases of one module and options with one query and one cquery."""
    expansions = bazel.expansions(module, (case["target"] for case, _ in cases.values()))
    fixtures = {
        key: fixture(case, api, expansions[case["target"]])
        for key, (case, api) in cases.items()
    }
    labels = [
        label
        for key, (case, _) in cases.items()
        for label in (case["target"], *fixtures[key].companions)
    ]
    try:
        observed = bazel.configured(module, labels, options)
    except EvidenceError as error:
        raise EvidenceError(f"cases {', '.join(cases)}: {error}") from error
    return {
        key: check_case(case, api, fixtures[key], observed)
        for key, (case, api) in cases.items()
    }


def check_cases(bazel: EvaluatedBazel, cases: Cases) -> dict[str, list[str]]:
    """
    Each case's diagnostics, with one query and one cquery per module and options.

    A repository case fetches its own facts, partly with other options, so it runs
    before its group's target cases, which then end the group on its own
    configuration; a group of repository cases alone may end on host execution.
    """
    errors = {}
    for module, options, keys in case_groups(cases):
        targets = {}
        for key in keys:
            case, api = cases[key]
            if "entrypoints" in case:
                errors[key] = check_repository(bazel, case, api.contract)
            else:
                targets[key] = cases[key]
        if targets:
            errors |= check_targets(bazel, module, options, targets)
    return {key: [f"{key}: {error}" for error in found] for key, found in errors.items()}


def lane_independent_errors(
    bazel: EvaluatedBazel,
    apis: Mapping[str, Api],
    manifest: dict[str, Any],
    public_targets: list[str],
) -> list[str]:
    """Lane-independent registry coverage and public targets."""
    errors = coverage_errors(apis, manifest["cases"], manifest["behavior"])
    return errors + check_public_targets(bazel, public_targets)


def behavior_errors(
    bazel: EvaluatedBazel, behavior: Mapping[str, list[Any]], lane: str
) -> list[str]:
    """Registered behavior tests that are no evaluated test, in the modules of a lane."""
    errors = []
    for module, labels in sorted(behavior_tests(behavior).items()):
        if behavior_lane(module) != lane:
            continue
        found = bazel.tests(labels, Module(Path(module), ()))
        for label in sorted(labels - found):
            where = "" if module == "." else f" (module {module})"
            errors.append(f"unresolved evaluated behavior test: {label}{where}")
    return errors


def lane_cases(
    cases: Mapping[str, dict[str, Any]], lane: str
) -> dict[str, dict[str, Any]]:
    """The configured cases of one lane, by key."""
    return {key: case for key, case in cases.items() if case["lane"] == lane}


def lane_errors(
    bazel: EvaluatedBazel,
    apis: Mapping[str, Api],
    cases: Mapping[str, dict[str, Any]],
    lane: str,
) -> list[str]:
    """Diagnostics of one lane's configured cases, in module, options and key order."""
    if not cases:
        return [f"{lane}: required lane contains no configured cases"]
    checked = {
        key: (case, api)
        for key, case in cases.items()
        if (api := apis.get(key.partition("#")[0])) is not None
    }
    results = check_cases(bazel, checked)
    order = sorted(
        checked, key=lambda key: (cases[key]["module"], cases[key]["options"], key)
    )
    return [error for key in order for error in results[key]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=CONTRACT_LANES, required=True)
    args = parser.parse_args()
    root = Path(os.environ["BUILD_WORKSPACE_DIRECTORY"])
    inventory = read_inventory(root / INVENTORY)
    bazel = EvaluatedBazel(root / RULESET)
    targets = {inventory_target(label): label for label in inventory["PUBLIC_APIS"]}
    manifest = json.loads(bazel.outputs([MANIFEST])[MANIFEST].read_text())
    modules = bazel.extracted(targets)
    apis, errors = extracted_apis(
        {targets[target]: module for target, module in modules.items()}
    )
    if args.lane == DEFAULT_CONTRACT_LANE:
        errors.extend(
            lane_independent_errors(
                bazel, apis, manifest, list(inventory["PUBLIC_TARGETS"])
            )
        )
    errors.extend(behavior_errors(bazel, manifest["behavior"], args.lane))
    cases = {key: host_case(case) for key, case in manifest["cases"].items()}
    selected = lane_cases(cases, args.lane)
    errors.extend(lane_errors(bazel, apis, selected, args.lane))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Bazel-evaluated {args.lane} API contracts passed ({len(selected)} cases).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, EvidenceError) as error:
        sys.exit(str(error))
