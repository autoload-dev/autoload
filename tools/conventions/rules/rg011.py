"""
RG011: reusable add-on implementation does not consume its demo.

Coverage is limited to direct authored inputs inside the workspace, resolved by Bazel to
their defining target or source file. Indirect dependency paths require review; this
rule does not claim a configured dependency-closure audit. Test inputs are RG012's.
"""

from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo


class AddonIndependence:
    info = RuleInfo(
        "RG011",
        "Reusable add-on implementation is independent of its demo",
        "rules_godot/docs/public/conventions.md#rg011",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for module in context.workspace.modules:
            checked: list[tuple[Location, frozenset[str]]] = []
            for declaration in context.declarations(module):
                location = declaration.call.location
                if (
                    self._scope(context.workspace, Path(location.path))
                    != "implementation"
                ):
                    continue
                for target in declaration.targets:
                    if target.booleans.get("testonly") is True:
                        continue
                    if "testonly" not in target.booleans:
                        yield Finding(
                            location,
                            f"cannot determine add-on implementation role for {target.label}",
                            "not_checked",
                        )
                        continue
                    checked.append((location, target.authored_inputs()))
            sources = context.sources(module, set().union(*(i for _, i in checked)))
            seen: set[tuple[Location, str]] = set()
            for location, inputs in checked:
                for label in sorted(inputs & sources.keys()):
                    if (
                        self._scope(context.workspace, sources[label]) == "demo"
                        and (location, label) not in seen
                    ):
                        seen.add((location, label))
                        yield Finding(
                            location,
                            f"reusable add-on implementation must not consume demo input {label}",
                        )

    @staticmethod
    def _scope(workspace: Workspace, path: Path) -> str | None:
        """Classify a path inside an add-on as implementation, demo or tests."""
        owner = workspace.typed_directory(path)
        if owner is None or owner[0] != "addons":
            return None
        parts = path.relative_to(owner[1]).parts
        if parts and parts[0] == "demo":
            return "demo"
        # Native test code stays with its backend, in any tests/ directory.
        if "tests" in parts[:-1]:
            return "tests"
        return "implementation"
