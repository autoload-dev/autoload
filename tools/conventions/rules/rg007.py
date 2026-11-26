"""RG007: Godot test operations and their generated helpers are test-only."""

from collections.abc import Iterable

from tools.conventions.context import Context, Target
from tools.conventions.framework import Finding, RuleInfo

# rules_godot's test operation, which the rule knows even without a test among its targets.
OPERATIONS = frozenset({"godot_test"})
# The rule class of the test that godot_test declares (rules_godot/godot/private/run.bzl).
TEST_RULE = "_godot_test"


def is_operation_test(target: Target) -> bool:
    """
    Whether a target is the Godot test its outermost macro declares under the macro's own
    name, as a test framework's test macro does, rather than a fixture of a test suite.
    """
    name = target.label.rpartition(":")[2]
    return target.kind == TEST_RULE and name == target.strings.get("generator_name")


def test_operations(context: Context) -> frozenset[str]:
    """godot_test and every macro that declares a Godot test under its own name."""
    return OPERATIONS.union(
        target.strings["generator_function"]
        for module in context.workspace.loaded_modules
        for target in context.bazel.rules(module)
        if is_operation_test(target) and target.strings.get("generator_function")
    )


class TestOnlyOperations:
    info = RuleInfo(
        "RG007",
        "Godot test operations and their helpers are test-only",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        known = test_operations(context)
        for module in context.workspace.loaded_modules:
            for declaration in context.declarations(module):
                call = declaration.call
                operations = [
                    target
                    for target in declaration.targets
                    if target.strings.get("generator_function") in known
                ]
                if not operations:
                    if call.kind in known:
                        yield Finding(
                            call.location,
                            "cannot identify test operation from Bazel generator metadata",
                            "not_checked",
                        )
                    continue
                for target in declaration.targets:
                    if target not in operations:
                        yield Finding(
                            call.location,
                            f"cannot attribute {target.label} to a Godot test operation",
                            "not_checked",
                        )
                for target in operations:
                    value = target.booleans.get("testonly")
                    if value is None:
                        yield Finding(
                            call.location,
                            f"cannot determine effective testonly for {target.label}",
                            "not_checked",
                        )
                    elif not value:
                        yield Finding(
                            call.location,
                            f"{target.label} must be testonly; remove testonly = False "
                            "from the test operation",
                        )
