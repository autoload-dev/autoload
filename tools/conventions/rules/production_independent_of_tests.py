"""
production-independent-of-tests: production targets do not consume test-owned inputs that
Bazel lets through.

A test scope is a tests/ directory below the root of a project or add-on, or elsewhere
below the root of its module. Paths are measured from the owning module, so a consumer
module's directory name, such as tests/, never makes a scope. A generator's template, a
`.tmpl` file, is no input of the scope it will become. Coverage is limited to direct
authored inputs inside the workspace. A test-only target is no subject: Bazel's test-only
dependency check rejects a production target that depends on it, so the rule judges source
files and the targets of test scopes that are not marked test-only.
"""

from collections.abc import Iterable
from pathlib import Path

from tools.addons.new import SUFFIX
from tools.conventions.context import Context, Location, Module, Target, Workspace
from tools.conventions.framework import Finding, RuleInfo


def test_scope(workspace: Workspace, path: Path) -> bool:
    if path.suffix == SUFFIX:
        return False
    root = workspace.project(path) or workspace.owner(path.as_posix())
    return "tests" in path.relative_to(root).parts[:-1]


def _test_only(context: Context, module: Module, labels: Iterable[str]) -> frozenset[str]:
    """The labels of test-only targets, whose consumers Bazel's test-only check guards."""
    facts = context.bazel.inspect(module, tuple(sorted(labels)))
    return frozenset(
        label
        for label, fact in facts.items()
        if isinstance(fact, Target) and fact.booleans.get("testonly") is True
    )


class ProductionIsolation:
    info = RuleInfo(
        "production-independent-of-tests",
        "Production targets are independent of test scopes",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for module in context.workspace.loaded_modules:
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
            guarded = _test_only(context, module, sources)
            seen: set[tuple[Location, str]] = set()
            for location, inputs in checked:
                for label in sorted(inputs & sources.keys() - guarded):
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
