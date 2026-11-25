"""RG007: Godot test operations and their generated helpers are test-only."""

from collections.abc import Iterable

from tools.conventions.context import Context, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.manifests import module_manifest
from tools.setup.modules import is_addon_module

# rules_godot's test operation; add-on modules declare theirs in addon.pkl's testOperations.
OPERATIONS = frozenset({"godot_test"})


def declared_operations(workspace: Workspace) -> frozenset[str]:
    """godot_test and the test operations the add-on modules of the workspace declare."""
    manifests = (
        module_manifest(workspace, module)
        for module in workspace.module_paths
        if is_addon_module(module)
    )
    return OPERATIONS.union(
        *(manifest["testOperations"] for manifest in manifests if manifest is not None)
    )


class TestOnlyOperations:
    info = RuleInfo(
        "RG007",
        "Godot test operations and their helpers are test-only",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        known = declared_operations(context.workspace)
        for module in context.workspace.modules:
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
