"""
Where the repository's consumers keep their projects and add-ons: the consumer roots of the
root module, the consumer modules and the typed roots measured from either.
"""

from pathlib import Path

from tools.addons.modules import example_projects
from tools.setup.modules import (
    ADDON_E2E,
    ADDON_EXAMPLES,
    ADDONS,
    RULESET,
    is_registry_test_module,
)

# The typed roots of a consumer, below its root: projects/ and addons/.
TYPED_ROOTS = frozenset({"projects", "addons"})
# The ruleset's module and documentation; the root and the ruleset are no consumer modules
# and have no typed roots of their own.
RULESET_MODULE = RULESET
DOCS = ("docs/", f"{RULESET_MODULE}/docs/")
NON_CONSUMER_MODULES = frozenset({Path("."), RULESET_MODULE})
# The consumers in the root module: its examples, each application a project directly in
# examples/, and the ruleset's consumer scenarios with their smoke paths.
EXAMPLES_ROOT = Path("examples")
REGRESSION_ROOT = Path("e2e/rules_godot")
CONSUMER_ROOTS = (EXAMPLES_ROOT, REGRESSION_ROOT)
SMOKE_ROOT = "smoke"
ADDON_SCENARIO = "shared_addon"


def scenario_directory(parts: tuple[str, ...]) -> tuple[str, Path] | None:
    """
    The kind and root of the consumer scenario that a path below e2e/rules_godot/, given by its
    parts, lies in: one project package per scenario and per operating system below smoke/;
    the shared add-on scenario is an add-on.
    """
    if parts[0] == SMOKE_ROOT and len(parts) > 2:
        return "projects", REGRESSION_ROOT / Path(*parts[:2])
    if parts[0] == ADDON_SCENARIO and len(parts) > 1:
        return "addons", REGRESSION_ROOT / ADDON_SCENARIO
    if parts[0] not in {SMOKE_ROOT, ADDON_SCENARIO} and len(parts) > 1:
        return "projects", REGRESSION_ROOT / parts[0]
    return None


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


def is_addon_test(root: Path | None) -> bool:
    """Whether a consumer is an add-on module's end-to-end tests, which have no typed roots."""
    return root is not None and root.parent == ADDON_E2E


def typed_directory(
    root: Path, path: Path, configured: frozenset[Path]
) -> tuple[str, Path] | None:
    """
    The kind and root of the project or add-on that path lies in, below the consumer root
    ``root``: a project directly in examples/ or an add-on module's examples, one of the
    scenarios' packages, or a directory of a consumer module's typed roots. ``configured``
    holds the directories with a project.godot.
    """
    if path == root or is_addon_test(root):
        return None
    parts = path.relative_to(root).parts
    if root == REGRESSION_ROOT:
        return scenario_directory(parts)
    if root.parent == ADDON_EXAMPLES or is_registry_test_module(root.as_posix()):
        project = flat_project(root, parts, configured)
        return None if project is None else ("projects", project)
    return consumer_directory(root, parts)


def flat_project(
    root: Path, parts: tuple[str, ...], configured: frozenset[Path]
) -> Path | None:
    """
    The project of a flat consumer, such as an add-on module's examples or a registry test
    module: the consumer itself, or a project directly in one of its directories.
    """
    projects = example_projects(root, configured)
    candidate = root if root in projects else root / parts[0]
    return candidate if candidate in projects else None


def consumer_directory(root: Path, parts: tuple[str, ...]) -> tuple[str, Path] | None:
    """A project directly in examples/, or a directory of a consumer module's typed roots."""
    if len(parts) > 2 and parts[0] in TYPED_ROOTS:
        return parts[0], root / Path(*parts[:2])
    if root == EXAMPLES_ROOT and len(parts) > 1:
        return "projects", root / parts[0]
    return None
