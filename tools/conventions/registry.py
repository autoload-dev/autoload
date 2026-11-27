"""Select enabled rules without adding rule-specific behavior to the checker."""

from tools.conventions import per_file
from tools.conventions.framework import Rule
from tools.conventions.rules.addon_module_examples_define_edit_and_pack import (
    AddonModuleExamplesDefineEditAndPack,
)
from tools.conventions.rules.addon_module_named_after_directory import (
    AddonModuleNamedAfterDirectory,
)
from tools.conventions.rules.addon_modules_own_template_files import (
    AddonModulesOwnTemplateFiles,
)
from tools.conventions.rules.application_content_under_main import (
    ApplicationContentUnderMain,
)
from tools.conventions.rules.application_tests_under_tests import (
    ApplicationTestsUnderTests,
)
from tools.conventions.rules.backends_under_native import BackendsUnderNative
from tools.conventions.rules.documented_targets_exist import CommandLabels
from tools.conventions.rules.engine_files_under_engines import EngineLayout
from tools.conventions.rules.godot_process_tests_tagged import GodotProcessTests
from tools.conventions.rules.linked_skills import SharedSkills
from tools.conventions.rules.no_component_names_in_tooling import NoComponentNames
from tools.conventions.rules.no_godot_in_addon_modules import NoGodotRunsInAddonModules
from tools.conventions.rules.no_stray_entries_in_addon_module_roots import (
    NoStrayEntriesInAddonModuleRoots,
)
from tools.conventions.rules.no_test_only_dependencies_in_addon_modules import (
    NoTestOnlyDependenciesInAddonModules,
)
from tools.conventions.rules.production_independent_of_tests import ProductionIsolation
from tools.conventions.rules.project_named_after_directory import ProjectTargetNames
from tools.conventions.rules.projects_at_fixed_places import ProjectPlaces
from tools.conventions.rules.registry_templates_have_their_module import (
    RegistryTemplatesHaveTheirModule,
)
from tools.conventions.rules.registry_test_module_in_bcr import RegistryTestModules
from tools.conventions.rules.release_archives_without_tests import ReleasedWithoutTests
from tools.conventions.rules.snake_case_target_names import TargetNames
from tools.conventions.rules.unique_extension_names import UniqueExtensionNames

# The rules of the add-on modules' layout, which every module the generator writes satisfies.
ADDON_MODULE_RULES: tuple[Rule, ...] = (
    AddonModuleNamedAfterDirectory(),
    AddonModulesOwnTemplateFiles(),
    RegistryTemplatesHaveTheirModule(),
    NoStrayEntriesInAddonModuleRoots(),
    NoTestOnlyDependenciesInAddonModules(),
    AddonModuleExamplesDefineEditAndPack(),
    UniqueExtensionNames(),
    BackendsUnderNative(),
)

# The rules that judge more than one file at a time, which the conventions tool runs.
RULES: tuple[Rule, ...] = (
    TargetNames(),
    CommandLabels(),
    ApplicationContentUnderMain(),
    ApplicationTestsUnderTests(),
    ProjectPlaces(),
    ProductionIsolation(),
    EngineLayout(),
    *ADDON_MODULE_RULES,
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
