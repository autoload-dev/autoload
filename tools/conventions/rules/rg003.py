"""RG003: target-producing authored BUILD calls pass name explicitly."""

from collections.abc import Iterable

from tools.conventions.context import Context
from tools.conventions.framework import Finding, RuleInfo


class ExplicitNames:
    info = RuleInfo(
        "RG003",
        "Target declarations pass name explicitly",
        "rules_godot/docs/public/conventions.md#rg003",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for module in context.workspace.modules:
            for declaration in context.declarations(module):
                call = declaration.call
                if "name" not in call.attrs:
                    yield Finding(call.location, f"{call.kind} must pass name explicitly")
