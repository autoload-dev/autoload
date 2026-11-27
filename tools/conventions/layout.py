"""
Where the repository's consumers keep their projects: the consumer roots of the root module,
the consumer modules and the fixed places of projects in either.
"""

from pathlib import Path

from tools.setup.modules import (
    ADDON_E2E,
    ADDON_EXAMPLES,
    ADDONS,
    EXAMPLES,
    RULESET,
    is_registry_test_module,
)

# The ruleset's module and documentation; the root and the ruleset are no consumer modules.
RULESET_MODULE = RULESET
DOCS = ("docs/", f"{RULESET_MODULE}/docs/")
NON_CONSUMER_MODULES = frozenset({Path("."), RULESET_MODULE})
# The consumers in the root module: its examples, each application a project directly in
# examples/, and the ruleset's consumer scenarios with their smoke paths.
EXAMPLES_ROOT = EXAMPLES
REGRESSION_ROOT = Path("e2e/rules_godot")
# The directory of custom engines, shared by the applications beside it and no project.
ENGINES = "engines"
CONSUMER_ROOTS = (EXAMPLES_ROOT, REGRESSION_ROOT)
# The directory of tests, at any depth of a module.
TESTS = "tests"
SMOKE_ROOT = "smoke"


def scenario_project(parts: tuple[str, ...]) -> Path | None:
    """
    The project of the consumer scenario that a path below e2e/rules_godot/, given by its
    parts, lies in: one project per scenario, and one per operating system below smoke/.
    """
    if parts[0] == SMOKE_ROOT:
        return REGRESSION_ROOT / Path(*parts[:2]) if len(parts) > 2 else None
    return REGRESSION_ROOT / parts[0] if len(parts) > 1 else None


def root_consumer(path: Path, modules: tuple[Path, ...]) -> Path | None:
    """
    The consumer in the root module that path belongs to: an add-on module's examples or
    end-to-end tests, when its module is among the modules, or else examples/ or
    e2e/rules_godot/.
    """
    for area in (ADDON_EXAMPLES, ADDON_E2E):
        if path.is_relative_to(area) and path != area:
            module = path.relative_to(area).parts[0]
            if Path(ADDONS) / module in modules:
                return area / module
    return next((root for root in CONSUMER_ROOTS if path.is_relative_to(root)), None)


def is_flat(root: Path) -> bool:
    """
    Whether a consumer is flat, one project or one per directory: an add-on module's
    examples or end-to-end tests, or a registry test module.
    """
    return root.parent in (ADDON_EXAMPLES, ADDON_E2E) or is_registry_test_module(root)


def is_application(project: Path) -> bool:
    """Whether a project is an application, a project directly in examples/."""
    return project.parent == EXAMPLES_ROOT


def is_end_to_end(project: Path) -> bool:
    """Whether a project is an add-on module's end-to-end test project, test-only as a whole."""
    return project.is_relative_to(ADDON_E2E)


def flat_project(
    root: Path, parts: tuple[str, ...], configured: frozenset[Path]
) -> Path | None:
    """
    The project of a flat consumer, such as an add-on module's examples or a registry test
    module: a project directly in one of its directories, such as a scenario or a
    configuration variant, or else the consumer itself.
    """
    if len(parts) > 1 and root / parts[0] in configured:
        return root / parts[0]
    return root if root in configured else None


def is_application_path(parts: tuple[str, ...]) -> bool:
    """Whether a path below examples/, given by its parts, lies in an application project."""
    return len(parts) > 1 and parts[0] != ENGINES


def project_directory(root: Path, path: Path, configured: frozenset[Path]) -> Path | None:
    """
    The project that path lies in, below the consumer root ``root``: a project directly in
    examples/, one of the scenarios' projects, or a project of a flat consumer.
    ``configured`` holds the directories with a project.godot.
    """
    if path == root:
        return None
    parts = path.relative_to(root).parts
    if root == REGRESSION_ROOT:
        return scenario_project(parts)
    if is_flat(root):
        return flat_project(root, parts, configured)
    if root == EXAMPLES_ROOT and is_application_path(parts):
        return root / parts[0]
    return None
