"""Select enabled rules without adding rule-specific behavior to the checker."""

from tools.conventions.framework import Rule
from tools.conventions.rules.rg001 import PackageNames
from tools.conventions.rules.rg002 import TargetNames
from tools.conventions.rules.rg003 import ExplicitNames
from tools.conventions.rules.rg004 import FixtureReferences
from tools.conventions.rules.rg006 import CommandLabels
from tools.conventions.rules.rg007 import TestOnlyOperations
from tools.conventions.rules.rg008 import ApplicationContent
from tools.conventions.rules.rg009 import ProjectPlaces
from tools.conventions.rules.rg012 import ProductionIsolation
from tools.conventions.rules.rg013 import PublicDocumentationLinks
from tools.conventions.rules.rg014 import EngineLayout
from tools.conventions.rules.rg015 import AddonModuleLayout
from tools.conventions.rules.rg016 import LocalLinks
from tools.conventions.rules.rg017 import AgentInstructions
from tools.conventions.rules.rg018 import SharedSkills
from tools.conventions.rules.rg019 import ProjectTargetNames
from tools.conventions.rules.rg020 import RegistryTestModules
from tools.conventions.rules.rg021 import NoGodotRunsInAddonModules
from tools.conventions.rules.rg023 import ReleasedWithoutTests

RULES: tuple[Rule, ...] = (
    PackageNames(),
    TargetNames(),
    ExplicitNames(),
    FixtureReferences(),
    CommandLabels(),
    TestOnlyOperations(),
    ApplicationContent(),
    ProjectPlaces(),
    ProductionIsolation(),
    PublicDocumentationLinks(),
    EngineLayout(),
    AddonModuleLayout(),
    LocalLinks(),
    AgentInstructions(),
    SharedSkills(),
    ProjectTargetNames(),
    RegistryTestModules(),
    NoGodotRunsInAddonModules(),
    ReleasedWithoutTests(),
)


def select(ids: list[str] | None = None) -> tuple[Rule, ...]:
    unknown = set(ids or []) - {rule.info.id for rule in RULES}
    if unknown:
        raise ValueError("Unknown convention rule IDs: " + ", ".join(sorted(unknown)))
    return tuple(rule for rule in RULES if ids is None or rule.info.id in ids)
