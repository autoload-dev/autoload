"""
Require real configured contract mismatches to fail through the production checker.

The ruleset's evaluated_mismatch_test (godot/tests/api_contracts) runs it with the evidence
of its mismatch fixtures, as a contract test runs contracts.py.
"""

import sys

from tools.docs.contracts import arguments, check_cases, read_test

_MODULE = "//godot/tests/api_contracts:mismatch.bzl%"

# API symbol -> expected diagnostics; none means it must pass.
SCENARIOS = {
    "good": [],
    "alias_files_companion": [],
    "missing_group": [
        "missing documented group: missing",
        "undocumented group: report",
    ],
    "executable_claim": ["promised test is not an evaluated Bazel test"],
    "pretend_test_companion": [
        "companion",
        "promised test is not an evaluated Bazel test",
    ],
    "alias_executable_companion": ["undocumented executable behavior"],
    # A helper visible only to another package is still a consumer interface.
    "restricted_companion": ["undocumented companion: {name}.unexpected"],
    # A symbolic macro's same-package grant reaches its caller's package.
    "same_package_leak": ["undocumented companion: {name}.unexpected"],
}


def main() -> None:
    test = read_test(arguments(sys.argv[1:]))
    assert not test.extraction_errors, test.extraction_errors
    assert set(test.plan["cases"]) == {_MODULE + symbol for symbol in SCENARIOS}
    results = check_cases(
        test.evidence,
        {key: (case, test.apis[key]) for key, case in test.plan["cases"].items()},
    )
    for symbol, expected in SCENARIOS.items():
        errors = results[_MODULE + symbol]
        if not expected:
            assert not errors, errors
        for diagnostic in expected:
            assert any(diagnostic in error for error in errors), (symbol, errors)
        outcome = "rejected evaluated mismatch" if expected else "matched source contract"
        print(f"{symbol}: {outcome}")


if __name__ == "__main__":
    main()
