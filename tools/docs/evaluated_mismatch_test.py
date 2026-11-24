"""Require real configured contract mismatches to fail through the production checker."""

import os
from pathlib import Path

from tools.docs.contracts import check_cases, extracted_apis, host_case
from tools.docs.evidence import ROOT_MODULE, EvaluatedBazel
from tools.setup.modules import RULESET

_FIXTURES = "//godot/tests/api_contracts:"

# API symbol -> (fixture target, expected diagnostics); none means it must pass.
SCENARIOS = {
    "good": ("evaluated_good", []),
    "alias_files_companion": ("evaluated_alias_files", []),
    "missing_group": (
        "evaluated_missing_group",
        ["missing documented group: missing", "undocumented group: report"],
    ),
    "executable_claim": (
        "evaluated_not_a_test",
        ["promised test is not an evaluated Bazel test"],
    ),
    "pretend_test_companion": (
        "evaluated_pretend_test_companion",
        ["companion", "promised test is not an evaluated Bazel test"],
    ),
    "alias_executable_companion": (
        "evaluated_alias_executable",
        ["undocumented executable behavior"],
    ),
    # A helper visible only to another package is still a consumer interface.
    "restricted_companion": (
        "evaluated_restricted_leak",
        ["undocumented companion: {name}.unexpected"],
    ),
    # A symbolic macro's same-package grant reaches its caller's package.
    "same_package_leak": (
        "evaluated_same_package_leak",
        ["undocumented companion: {name}.unexpected"],
    ),
}


def main() -> None:
    bazel = EvaluatedBazel(Path(os.environ["BUILD_WORKSPACE_DIRECTORY"]) / RULESET)
    inventory = _FIXTURES + "evaluated_mismatch_inventory.textproto"
    module = bazel.extracted([inventory], ROOT_MODULE)[inventory]
    apis, errors = extracted_apis({_FIXTURES + "mismatch.bzl": module})
    assert not errors, errors
    identities = {symbol: _FIXTURES + "mismatch.bzl%" + symbol for symbol in SCENARIOS}
    results = check_cases(
        bazel,
        {
            identities[symbol]: (
                host_case({"target": _FIXTURES + target}),
                apis[identities[symbol]],
            )
            for symbol, (target, _) in SCENARIOS.items()
        },
    )
    for symbol, (_, expected) in SCENARIOS.items():
        errors = results[identities[symbol]]
        if not expected:
            assert not errors, errors
        for diagnostic in expected:
            assert any(diagnostic in error for error in errors), (symbol, errors)
        outcome = "rejected evaluated mismatch" if expected else "matched source contract"
        print(f"{symbol}: {outcome}")


if __name__ == "__main__":
    main()
