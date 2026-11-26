"""RG007: Godot test operations and their generated helpers are test-only."""

from collections.abc import Iterable

from tools.conventions.context import Context, Declaration, Location, Target
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.operations import godot_test_operations


def testonly_findings(location: Location, target: Target) -> Iterable[Finding]:
    """The finding of a test operation's target whose effective testonly is not True."""
    value = target.booleans.get("testonly")
    if value is None:
        yield Finding(
            location,
            f"cannot determine effective testonly for {target.label}",
            "not_checked",
        )
    elif not value:
        yield Finding(
            location,
            f"{target.label} must be testonly; remove testonly = False "
            "from the test operation",
        )


def declaration_findings(
    declaration: Declaration, known: frozenset[str]
) -> Iterable[Finding]:
    """The findings of one declaration, which the rule checks if it calls a test operation."""
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
        return
    yield from (
        Finding(
            call.location,
            f"cannot attribute {target.label} to a Godot test operation",
            "not_checked",
        )
        for target in declaration.targets
        if target not in operations
    )
    for target in operations:
        yield from testonly_findings(call.location, target)


class TestOnlyOperations:
    info = RuleInfo(
        "RG007",
        "Godot test operations and their helpers are test-only",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        known = godot_test_operations(context)
        for module in context.workspace.loaded_modules:
            for declaration in context.declarations(module):
                yield from declaration_findings(declaration, known)
