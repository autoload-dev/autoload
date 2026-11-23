"""Compare evaluated public source contracts with configured, evaluated Bazel fixtures."""

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.conventions.context import EvidenceError, Module, Target
from tools.docs.api_docs import read_inventory
from tools.docs.coverage import ModuleInfo, module_apis
from tools.docs.evidence import EvaluatedBazel, behavior_tests, is_test
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

MANIFEST = "//godot/tests/api_contracts:case_manifest.json"


def inventory_target(module: str) -> str:
    """The unfiltered evaluated extraction of one public API module."""
    page = module.removeprefix("//").replace("/", "_").replace(":", "_")
    return "//public/api:" + page.removesuffix(".bzl") + "_inventory.textproto"


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


def check_case(
    bazel: EvaluatedBazel,
    identity: str,
    case: dict[str, Any],
    api: Api,
) -> list[str]:
    """Compare one source contract with a configured fixture and its expansion."""
    if "entrypoints" in case:
        errors = check_repository(bazel, case, api.contract)
        return [f"{identity}: {error}" for error in errors]
    module = Module(Path(case["module"]), ())
    label = case["target"]
    package, _, root = label.rpartition(":")
    loaded = {
        target.label.partition("//")[2]: target
        for target in bazel.expansion(module, label)
    }
    root_fact = loaded[label.partition("//")[2]]
    errors = []
    companions = {}
    for row in active(api.contract.companions, case["conditions"]):
        pattern = row["name"]
        companion = package + ":" + pattern.replace("{name}", root, 1)
        if not pattern.startswith("{name}") or "{" in companion:
            errors.append(f"unresolved generated companion pattern {pattern}")
        elif companion.partition("//")[2] not in loaded:
            errors.append(f"missing evaluated loading facts for {companion}")
        else:
            companions[companion] = row
    observed = bazel.configured(module, (label, *companions), case["options"])
    for companion, row in companions.items():
        errors.extend(
            f"companion {companion} {error}"
            for error in companion_errors(
                row, loaded[companion.partition("//")[2]], root_fact, observed[companion]
            )
        )
    discovered = {
        "{name}" + name.removeprefix(root) if name.startswith(root) else name
        for target in loaded.values()
        if (name := target.label.rpartition(":")[2]) != root
        and has_consumer_visibility(
            target.label,
            target.label_lists.get("visibility", ()),
            symbolic_macro=api.kind == "macro_info",
        )
    }
    errors.extend(
        compare(
            api.contract,
            observed[label],
            test=is_test(root_fact),
            shared_library=is_shared_library(root_fact.kind, root_fact.booleans),
            companions=discovered,
            conditions=case["conditions"],
            forwarded_groups=case.get("forwarded_groups", False),
        )
    )
    return [f"{identity}: {error}" for error in errors]


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=CONTRACT_LANES, required=True)
    args = parser.parse_args()
    root = Path(os.environ["BUILD_WORKSPACE_DIRECTORY"])
    inventory = read_inventory(root / "public/api/modules.bzl")
    bazel = EvaluatedBazel(root.parent)
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
    selected = sorted(
        (case["module"], case["options"], key)
        for key, case in cases.items()
        if case["lane"] == args.lane
    )
    for _, _, key in selected:
        api = apis.get(key.partition("#")[0])
        if api is not None:
            errors.extend(check_case(bazel, key, cases[key], api))
    if not selected:
        errors.append(f"{args.lane}: required lane contains no configured cases")
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
