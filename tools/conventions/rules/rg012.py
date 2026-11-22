"""
RG012: production targets do not consume test-owned inputs.

A test scope is a tests/ directory below the root of a project or add-on, or elsewhere
below the root of its module. Paths are measured from the owning module, so a consumer
module's directory name, such as tests/, never makes a scope. Coverage is limited to
direct authored inputs inside the workspace.
"""

from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo


def test_scope(workspace: Workspace, path: Path) -> bool:
    owner = workspace.typed_directory(path)
    root = owner[1] if owner is not None else workspace.owner(path.as_posix())
    return "tests" in path.relative_to(root).parts[:-1]


class ProductionIsolation:
    info = RuleInfo(
        "RG012",
        "Production targets are independent of test scopes",
        "rules_godot/docs/public/conventions.md#rg012",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for module in context.workspace.modules:
            checked: list[tuple[Location, frozenset[str]]] = []
            for declaration in context.declarations(module):
                location = declaration.call.location
                if test_scope(context.workspace, Path(location.path)):
                    continue
                for target in declaration.targets:
                    if target.booleans.get("testonly") is True:
                        continue
                    if "testonly" not in target.booleans:
                        yield Finding(
                            location,
                            f"cannot determine production role for {target.label}",
                            "not_checked",
                        )
                        continue
                    checked.append((location, target.authored_inputs()))
            sources = context.sources(module, set().union(*(i for _, i in checked)))
            seen: set[tuple[Location, str]] = set()
            for location, inputs in checked:
                for label in sorted(inputs & sources.keys()):
                    if (
                        test_scope(context.workspace, sources[label])
                        and (location, label) not in seen
                    ):
                        seen.add((location, label))
                        yield Finding(
                            location,
                            f"production target must not consume test-owned input {label}; "
                            "mark the consumer testonly or move the input out of tests/",
                        )
