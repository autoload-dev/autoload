"""
application-tests-under-tests: an application's tests live in its tests/ package, never in
its project's root package.
"""

from collections.abc import Iterable

from tools.conventions.context import BUILD_FILES, Context
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.layout import EXAMPLES_ROOT
from tools.conventions.operations import godot_test_operations


def is_test(kind: str, operations: frozenset[str]) -> bool:
    """Whether a call declares a test: a test operation or a rule named like one."""
    return kind in operations or kind.endswith("_test")


class ApplicationTestsUnderTests:
    info = RuleInfo(
        "application-tests-under-tests",
        "An application's tests live in its tests/ package",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        kinds = godot_test_operations(context)
        roots = {
            (project / build).as_posix(): project
            for project in workspace.projects
            if project.is_relative_to(EXAMPLES_ROOT)
            for build in BUILD_FILES
        }
        for call in context.calls:
            project = roots.get(call.location.path)
            if project is not None and is_test(call.kind, kinds):
                yield Finding(
                    call.location,
                    f"an application's tests live in {project / 'tests'}/: "
                    f":{call.literal_name}",
                )
