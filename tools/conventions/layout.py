"""
Where the repository's consumers keep their projects and add-ons: the consumer roots of the
root module, the consumer modules and the typed roots measured from either.
"""

from pathlib import Path

from tools.setup.modules import RULESET

# The typed roots of a consumer, below its root: projects/ and addons/.
TYPED_ROOTS = frozenset({"projects", "addons"})
# The ruleset's module and documentation; the root and the ruleset are no consumer modules
# and have no typed roots of their own.
RULESET_MODULE = RULESET
DOCS = ("docs/", f"{RULESET_MODULE}/docs/")
NON_CONSUMER_MODULES = frozenset({Path("."), RULESET_MODULE})
# The consumers in the root module: its examples, with typed roots, and the ruleset's consumer
# scenarios with their smoke paths.
EXAMPLES_ROOT = Path("examples")
REGRESSION_ROOT = Path("scenarios")
CONSUMER_ROOTS = (EXAMPLES_ROOT, REGRESSION_ROOT)
# Each add-on module's example applications and Godot tests, a consumer of its own:
# examples/addons/<module>/ for every module addons/<module>/.
ADDON_EXAMPLES = EXAMPLES_ROOT / "addons"
# The Godot tests of an add-on module's examples: white-box fixtures, no typed root.
ADDON_TESTS = "tests"
SMOKE_ROOT = "smoke"
# Packages of the scenarios that are no scenario, such as shared tools.
REGRESSION_TOOLING = frozenset({"tools"})
ADDON_SCENARIO = "shared_addon"


def scenario_directory(parts: tuple[str, ...]) -> tuple[str, Path] | None:
    """
    The kind and root of the consumer scenario that a path below scenarios/, given by its
    parts, lies in: one project package per scenario and per operating system below smoke/;
    the shared add-on scenario is an add-on.
    """
    if parts[0] == SMOKE_ROOT and len(parts) > 2:
        return "projects", REGRESSION_ROOT / Path(*parts[:2])
    if parts[0] == ADDON_SCENARIO and len(parts) > 1:
        return "addons", REGRESSION_ROOT / ADDON_SCENARIO
    if (
        parts[0] not in REGRESSION_TOOLING | {SMOKE_ROOT, ADDON_SCENARIO}
        and len(parts) > 1
    ):
        return "projects", REGRESSION_ROOT / parts[0]
    return None


def root_consumer(path: Path, modules: tuple[Path, ...]) -> Path | None:
    """
    The consumer in the root module that path belongs to: an add-on module's examples, when
    its module is among the modules, or else examples/ or scenarios/.
    """
    if path.is_relative_to(ADDON_EXAMPLES) and path != ADDON_EXAMPLES:
        module = path.relative_to(ADDON_EXAMPLES).parts[0]
        if Path("addons") / module in modules:
            return ADDON_EXAMPLES / module
    return next((root for root in CONSUMER_ROOTS if path.is_relative_to(root)), None)


def is_addon_test(path: Path, root: Path | None) -> bool:
    """Whether path lies in the Godot tests of an add-on module's examples."""
    return (
        root is not None
        and root.parent == ADDON_EXAMPLES
        and path.relative_to(root).parts[:1] == (ADDON_TESTS,)
    )


def typed_directory(root: Path, path: Path) -> tuple[str, Path] | None:
    """
    The kind and root of the project or add-on directory ``<consumer>/<kind>/<name>/`` that
    path lies in, below the consumer root ``root``; the scenarios' packages are their projects.
    """
    if path == root:
        return None
    parts = path.relative_to(root).parts
    if root == REGRESSION_ROOT:
        return scenario_directory(parts)
    if len(parts) > 2 and parts[0] in TYPED_ROOTS:
        return parts[0], root / Path(*parts[:2])
    return None
