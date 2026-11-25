"""RG021: add-on modules run no Godot; their end-to-end tests live in the root module."""

from collections.abc import Iterable
from pathlib import Path

from tools.addons.modules import addon_manifest
from tools.conventions.context import Context, Location, Module
from tools.conventions.framework import Finding, RuleInfo
from tools.setup.modules import ADDONS

# The calls that make a Godot project or run Godot, besides a module's own test operations.
GODOT_RUNS = frozenset({"godot_project", "godot_test", "godot_metadata_sync"})


def is_addon_module(module: Path) -> bool:
    return module.parent == Path(ADDONS)


class NoGodotRunsInAddonModules:
    info = RuleInfo(
        "RG021",
        "Add-on modules run no Godot; their end-to-end tests live in the root module",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        for name in workspace.files:
            if Path(name).name == "project.godot" and is_addon_module(
                workspace.owner(name)
            ):
                yield Finding(Location(name, 1), self.message("a Godot project"))
        for module in workspace.modules:
            if is_addon_module(module.path):
                yield from self.runs(context, module)

    def runs(self, context: Context, module: Module) -> Iterable[Finding]:
        workspace = context.workspace
        path = (module.path / "addon.pkl").as_posix()
        manifest = workspace.text(path) if path in workspace.file_set else ""
        kinds = GODOT_RUNS | set(addon_manifest(manifest)["testOperations"])
        for call in context.starlark.calls(module):
            owned = workspace.owner(call.location.path) == module.path
            if owned and call.kind in kinds:
                yield Finding(call.location, self.message(call.kind))

    @staticmethod
    def message(what: str) -> str:
        return (
            f"{what} uses Godot as an application does: add-on modules hold unit tests "
            "only, and end-to-end tests live in the root module's e2e/addons/<module>/"
        )
