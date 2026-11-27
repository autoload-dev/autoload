"""Select enabled rules without adding rule-specific behavior to the checker."""

from tools.conventions import per_file
from tools.conventions.framework import Rule
from tools.conventions.rules.rg001 import PackageNames
from tools.conventions.rules.rg002 import TargetNames
from tools.conventions.rules.rg006 import CommandLabels
from tools.conventions.rules.rg007 import TestOnlyOperations
from tools.conventions.rules.rg008 import ApplicationContent
from tools.conventions.rules.rg009 import ProjectPlaces
from tools.conventions.rules.rg012 import ProductionIsolation
from tools.conventions.rules.rg014 import EngineLayout
from tools.conventions.rules.rg015 import AddonModuleLayout
from tools.conventions.rules.rg017 import AgentInstructions
from tools.conventions.rules.rg018 import SharedSkills
from tools.conventions.rules.rg019 import ProjectTargetNames
from tools.conventions.rules.rg020 import RegistryTestModules
from tools.conventions.rules.rg021 import NoGodotRunsInAddonModules
from tools.conventions.rules.rg022 import NoComponentNames
from tools.conventions.rules.rg023 import ReleasedWithoutTests
from tools.conventions.rules.rg026 import GodotProcessTests

# The rules that judge more than one file at a time, which the conventions tool runs.
RULES: tuple[Rule, ...] = (
    PackageNames(),
    TargetNames(),
    CommandLabels(),
    TestOnlyOperations(),
    ApplicationContent(),
    ProjectPlaces(),
    ProductionIsolation(),
    EngineLayout(),
    AddonModuleLayout(),
    AgentInstructions(),
    SharedSkills(),
    ProjectTargetNames(),
    RegistryTestModules(),
    NoGodotRunsInAddonModules(),
    NoComponentNames(),
    ReleasedWithoutTests(),
    GodotProcessTests(),
)


# Every registered rule, those of the lint check (per_file.py) included.
ALL_RULES = RULES + per_file.RULES


def select(ids: list[str] | None = None) -> tuple[Rule, ...]:
    """The rules of the IDs, or else those the conventions tool runs."""
    unknown = set(ids or []) - {rule.info.id for rule in ALL_RULES}
    if unknown:
        raise ValueError("Unknown convention rule IDs: " + ", ".join(sorted(unknown)))
    if ids is None:
        return RULES
    return tuple(rule for rule in ALL_RULES if rule.info.id in ids)
