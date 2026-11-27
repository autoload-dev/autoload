"""
The Godot test operations: godot_test and the macros that declare a Godot test under their own
name, which RG007, application-content and no-godot-in-addon-modules recognize by Bazel's
evidence rather than by a list.
"""

from tools.conventions.context import Context, Target

# rules_godot's test operation, known even where its targets show no Godot test.
OPERATIONS = frozenset({"godot_test"})
# The rule class of the test that godot_test declares (rules_godot/godot/private/run.bzl).
TEST_RULE = "_godot_test"


def is_operation_test(target: Target) -> bool:
    """
    Whether a target is the Godot test its outermost macro declares under the macro's own
    name, as a test framework's test macro does, rather than a fixture of a test suite.
    """
    name = target.label.rpartition(":")[2]
    return (
        target.kind == TEST_RULE
        and name == target.strings.get("generator_name")
        and "generator_function" in target.strings
    )


def godot_test_operations(context: Context) -> frozenset[str]:
    """godot_test and every macro that declares a Godot test under its own name."""
    return OPERATIONS.union(
        target.strings["generator_function"]
        for module in context.workspace.loaded_modules
        for target in context.bazel.rules(module)
        if is_operation_test(target)
    )
