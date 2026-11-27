"""Select enabled rules without adding rule-specific behavior to the checker."""

from tools.conventions import per_file
from tools.conventions.framework import Rule
from tools.conventions.rules.addon_module_layout import AddonModuleLayout
from tools.conventions.rules.application_content import ApplicationContent
from tools.conventions.rules.documented_targets_exist import CommandLabels
from tools.conventions.rules.engine_files_under_engines import EngineLayout
from tools.conventions.rules.linked_skills import SharedSkills
from tools.conventions.rules.no_component_names_in_tooling import NoComponentNames
from tools.conventions.rules.no_godot_in_addon_modules import NoGodotRunsInAddonModules
from tools.conventions.rules.project_named_after_directory import ProjectTargetNames
from tools.conventions.rules.projects_at_fixed_places import ProjectPlaces
from tools.conventions.rules.registry_test_module_in_bcr import RegistryTestModules
from tools.conventions.rules.release_archives_without_tests import ReleasedWithoutTests
from tools.conventions.rules.rg002 import TargetNames
from tools.conventions.rules.rg007 import TestOnlyOperations
from tools.conventions.rules.rg012 import ProductionIsolation
from tools.conventions.rules.rg026 import GodotProcessTests

# The rules that judge more than one file at a time, which the conventions tool runs.
RULES: tuple[Rule, ...] = (
    TargetNames(),
    CommandLabels(),
    TestOnlyOperations(),
    ApplicationContent(),
    ProjectPlaces(),
    ProductionIsolation(),
    EngineLayout(),
    AddonModuleLayout(),
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


def select(names: list[str] | None = None) -> tuple[Rule, ...]:
    """The rules of the names, or else those the conventions tool runs."""
    unknown = set(names or []) - {rule.info.name for rule in ALL_RULES}
    if unknown:
        raise ValueError("Unknown convention rules: " + ", ".join(sorted(unknown)))
    if names is None:
        return RULES
    return tuple(rule for rule in ALL_RULES if rule.info.name in names)
