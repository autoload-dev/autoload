"""RG021: add-on modules run no Godot; their end-to-end tests live in the root module."""

from collections.abc import Iterable

from tools.conventions.context import Context, Location, Module, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.operations import godot_test_operations
from tools.setup.modules import is_addon_module

# The calls that make a Godot project or run Godot, besides the macros that declare a
# Godot test (RG007).
GODOT_RUNS = frozenset(
    {"godot_project", "godot_test", "godot_metadata_sync", "godot_runtime_profile"}
)


class NoGodotRunsInAddonModules:
    info = RuleInfo(
        "RG021",
        "Add-on modules run no Godot; their end-to-end tests live in the root module",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        yield from self.projects(context.workspace)
        kinds = GODOT_RUNS | godot_test_operations(context)
        for module in context.workspace.modules:
            if is_addon_module(module.path):
                yield from self.runs(context, module, kinds)

    def projects(self, workspace: Workspace) -> Iterable[Finding]:
        for path in sorted(workspace.godot_configurations):
            if is_addon_module(workspace.owner(path.as_posix())):
                yield Finding(
                    Location(path.as_posix(), 1), self.message("a Godot project")
                )

    def runs(
        self, context: Context, module: Module, kinds: frozenset[str]
    ) -> Iterable[Finding]:
        workspace = context.workspace
        for call in context.starlark.calls(module):
            if call.kind in kinds and workspace.owner(call.location.path) == module.path:
                yield Finding(call.location, self.message(call.kind))

    @staticmethod
    def message(what: str) -> str:
        return (
            f"{what} uses Godot as an application does: add-on modules hold unit tests "
            "only, and end-to-end tests live in the root module's e2e/addons/<module>/"
        )
