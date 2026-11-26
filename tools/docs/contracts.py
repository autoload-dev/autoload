"""
Compare evaluated public source contracts with configured, evaluated Bazel fixtures.

The ruleset's contract tests (godot/tests/api_contracts/contract_test.bzl) run this module
with their evidence as declared inputs: the extracted documentation, the fixtures' loading
facts and their configured facts per configuration.

Sections: Case checks, Test.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.conventions.context import EvidenceError, Target
from tools.docs.coverage import ModuleInfo, module_apis, parse_module
from tools.docs.evidence import (
    Evidence,
    Labels,
    decode_configured,
    decode_loading,
    invocation,
    unqualified,
)
from tools.docs.output_contracts import (
    Api,
    ConfiguredTarget,
    active,
    compare,
    coverage_errors,
    has_consumer_visibility,
    is_shared_library,
    kind_errors,
)
from tools.docs.public_contracts import check_public_libraries, check_public_targets
from tools.docs.repository_contracts import check_repository
from tools.docs.ruleset import strip_repo

# ==== Case checks =============================================================


def companion_errors(
    row: dict[str, str], loaded: Target, root: Target, target: ConfiguredTarget
) -> list[str]:
    """Compare one documented companion with its loading and configured facts."""
    errors = kind_errors(
        row["kind"],
        target,
        test=loaded.is_test,
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
        elif pattern not in case["companions"]:
            unresolved.append(f"the case does not analyze its companion {pattern}")
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
            test=root_fact.is_test,
            shared_library=is_shared_library(root_fact.kind, root_fact.booleans),
            companions=discovered_companions(label.rpartition(":")[2], api, facts.loaded),
            conditions=case["conditions"],
            forwarded_groups=case.get("forwarded_groups", False),
        )
    )
    return errors


def check_target(evidence: Evidence, case: dict[str, Any], api: Api) -> list[str]:
    """Check a target case against its loading and configured facts."""
    facts = fixture(
        case, api, invocation(case["target"], evidence.loading.rules.values())
    )
    observed = evidence.configured(case["settings"], [case["target"], *facts.companions])
    return check_case(case, api, facts, observed)


# Contract cases with their extracted API, by case key.
Cases = Mapping[str, tuple[dict[str, Any], Api]]


def check_cases(evidence: Evidence, cases: Cases) -> dict[str, list[str]]:
    """Each case's diagnostics, attributed to its key."""
    errors = {}
    for key, (case, api) in cases.items():
        try:
            found = (
                check_repository(evidence, case, api.contract)
                if "entrypoints" in case
                else check_target(evidence, case, api)
            )
        except EvidenceError as error:
            raise EvidenceError(f"case {key}: {error}") from error
        errors[key] = [f"{key}: {error}" for error in found]
    return errors


# ==== Test ====================================================================


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


@dataclass(frozen=True)
class Test:
    """One contract test's inputs: its plan, evidence and the extracted APIs."""

    plan: dict[str, Any]
    evidence: Evidence
    apis: Mapping[str, Api]
    extraction_errors: list[str]
    manifest: dict[str, Any] | None


def read_test(args: argparse.Namespace) -> Test:
    plan = json.loads(args.plan.read_text())
    labels = Labels(plan["canonical"])
    tests = (
        frozenset(map(labels.apparent, args.behavior.read_text().split()))
        if args.behavior
        else frozenset()
    )
    evidence = Evidence(
        decode_loading(args.loading.read_text(), labels),
        tuple(decode_configured(path.read_text()) for path in args.evidence),
        tests,
    )
    modules = {}
    for path in args.extracted:
        module = parse_module(path.read_text())
        modules[strip_repo(module.file)] = module
    apis, errors = extracted_apis(modules)
    manifest = json.loads(args.manifest.read_text()) if args.manifest else None
    return Test(plan, evidence, apis, errors, manifest)


def behavior_errors(behavior: Mapping[str, list[str]], tests: Iterable[str]) -> list[str]:
    """Registered behavior tests that are no evaluated test."""
    registered = {test for labels in behavior.values() for test in labels}
    return [
        f"unresolved evaluated behavior test: {label}"
        for label in sorted(registered - set(tests))
    ]


def test_errors(test: Test) -> list[str]:
    """Every diagnostic of one contract test."""
    plan = test.plan
    errors = list(test.extraction_errors)
    if test.manifest is not None:
        errors.extend(
            coverage_errors(
                test.apis,
                test.manifest["cases"],
                test.manifest["behavior"],
                test.manifest["requirements"],
            )
        )
    errors.extend(behavior_errors(plan["behavior"], test.evidence.tests))
    errors.extend(check_public_targets(test.evidence, plan["public_targets"]))
    errors.extend(check_public_libraries(test.evidence, plan["libraries"]))
    cases = {
        key: (case, api)
        for key, case in plan["cases"].items()
        if (api := test.apis.get(key.partition("#")[0])) is not None
    }
    # The coverage of the registry, where a test checks it, reports these already.
    if test.manifest is None:
        errors.extend(
            f"{key}: case refers to unknown API"
            for key in sorted(plan["cases"].keys() - cases)
        )
    results = check_cases(test.evidence, cases)
    errors.extend(error for key in sorted(results) for error in results[key])
    return errors


def arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--loading", type=Path, required=True)
    parser.add_argument("--behavior", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--extracted", type=Path, action="append", default=[])
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    test = read_test(arguments(argv))
    errors = test_errors(test)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Bazel-evaluated API contracts passed ({len(test.plan['cases'])} cases).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, OSError, EvidenceError) as error:
        sys.exit(str(error))
