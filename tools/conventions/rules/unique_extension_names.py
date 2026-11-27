"""
unique-extension-names: no two add-on modules' extensions share a name, since on iOS it
names the extension's framework and an application's frameworks share one directory.
"""

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tools.conventions.addon_modules import addon_module_paths
from tools.conventions.context import Call, Context
from tools.conventions.framework import Finding, RuleInfo

# The rule of an add-on's extension, whose name names its framework on iOS.
EXTENSION = "godot_cc_extension"


def in_modules(name: str, modules: list[Path]) -> bool:
    return any(Path(name).is_relative_to(module) for module in modules)


def extension_owners(
    calls: Iterable[Call], modules: list[Path]
) -> dict[str | None, list[Call]]:
    """The calls in the modules that declare each extension, by name, in their order."""
    owners: dict[str | None, list[Call]] = defaultdict(list)
    for call in calls:
        if call.kind == EXTENSION and in_modules(call.location.path, modules):
            owners[call.literal_name].append(call)
    return owners


class UniqueExtensionNames:
    info = RuleInfo(
        "unique-extension-names",
        "No two add-on modules' extensions share a name",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        modules = addon_module_paths(context.workspace)
        owners = extension_owners(context.calls, modules)
        for call in owners.pop(None, []):
            yield Finding(
                call.location, f"cannot read the name of this {EXTENSION}", "not_checked"
            )
        for extension, owning in sorted(owners.items()):
            first = owning[0].location.path
            for call in owning[1:]:
                yield Finding(
                    call.location, f"extension name {extension} is taken by {first}"
                )
