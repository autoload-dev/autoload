"""
Discover every source module, then check the API inventory and its documentation.

Sections: Labels, Inventory, Bazel.
"""

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.conventions.environment import nested_tool_environment
from tools.docs.ruleset import INVENTORY
from tools.setup.modules import RULESET, label_path

# ==== Labels ==================================================================


def module_label(path: Path) -> str:
    return f"//{path.parent.as_posix()}:{path.name}"


def package(label: str) -> str:
    return label.removeprefix("//").split(":")[0]


def is_private(label: str) -> bool:
    return "private" in package(label).split("/")


def is_white_box_test(label: str) -> bool:
    return "tests" in package(label).split("/")


def documented_target(label: str) -> bool:
    """Whether a public rule target under //godot belongs in PUBLIC_TARGETS."""
    return not (is_private(label) or is_white_box_test(label))


# ==== Inventory ===============================================================

ROLES = (
    "PUBLIC_APIS",
    "CROSS_REPOSITORY_MODULES",
    "SUPPORT_MODULES",
)


def read_inventory(manifest: Path) -> dict[str, Any]:
    tree = ast.parse(manifest.read_text())
    return {
        target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(target := node.targets[0], ast.Name)
    }


def actual_modules(root: Path) -> set[str]:
    """The ruleset's modules; white-box tests in tests/ subpackages load private files but are no API modules."""
    return {
        label
        for path in (root / "godot").rglob("*.bzl")
        if not is_white_box_test(label := module_label(path.relative_to(root)))
    }


def module_role_errors(
    label: str, role: str, previous: str | None, actual: set[str]
) -> list[str]:
    errors = []
    if previous:
        errors.append(f"{label}: multiple module roles ({previous}, {role})")
    if label not in actual:
        errors.append(f"{role}: stale module {label}")
    if role == "SUPPORT_MODULES" and not is_private(label):
        errors.append(
            f"{label}: support modules must be private implementation files; classify loadable contracts explicitly"
        )
    return errors


def role_errors(inventory: dict[str, Any], actual: set[str]) -> list[str]:
    """Each module has exactly one role, the inventory lists only modules that exist."""
    errors = []
    # The other roles are dicts, so only this list can repeat a module.
    if len(inventory["SUPPORT_MODULES"]) != len(set(inventory["SUPPORT_MODULES"])):
        errors.append("SUPPORT_MODULES: duplicate modules")
    declared: dict[str, str] = {}
    for role in ROLES:
        for label in inventory[role]:
            errors.extend(module_role_errors(label, role, declared.get(label), actual))
            declared[label] = role
    errors.extend(
        f"{label}: unclassified new module; declare its API role in tools/docs/api/modules.bzl"
        for label in sorted(actual - set(declared))
    )
    return errors


def entrypoint_errors(inventory: dict[str, Any]) -> list[str]:
    """Public entrypoints name their symbols, cross-repository modules their purpose."""
    errors = [
        f"{label}: public entrypoints need primary symbols"
        for label, symbols in inventory["PUBLIC_APIS"].items()
        if not symbols
    ]
    errors.extend(
        f"{label}: cross-repository modules need a cross-repository load explanation"
        for label, purpose in inventory["CROSS_REPOSITORY_MODULES"].items()
        if not purpose.strip()
    )
    return errors


def visibility_specs(path: Path) -> list[Any]:
    """The arguments of a module's top-level visibility() calls."""
    return [
        ast.literal_eval(node.value.args[0])
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "visibility"
    ]


def is_public(spec: Any) -> bool:
    return spec == "public" or isinstance(spec, list) and "public" in spec


def module_visibility_errors(
    label: str, specs: list[Any], cross_repository: bool
) -> list[str]:
    public = any(map(is_public, specs))
    errors = []
    if not specs and not cross_repository:
        errors.append(
            f"{label}: support modules need explicit restricted load visibility"
        )
    if cross_repository and not public:
        errors.append(
            f"{label}: cross-repository modules need explicit public load visibility"
        )
    elif not cross_repository and public:
        errors.append(f"{label}: support modules cannot have public load visibility")
    return errors


def visibility_errors(root: Path, inventory: dict[str, Any]) -> list[str]:
    """Support modules restrict their load visibility, cross-repository modules make it public."""
    cross_repository = inventory["CROSS_REPOSITORY_MODULES"]
    errors = []
    for label in [*inventory["SUPPORT_MODULES"], *cross_repository]:
        path = label_path(root, label)
        if path.is_file():
            errors.extend(
                module_visibility_errors(
                    label, visibility_specs(path), label in cross_repository
                )
            )
    return errors


def returns_value(function: ast.FunctionDef) -> bool:
    return any(
        isinstance(child, ast.Return) and child.value is not None
        for child in ast.walk(function)
    )


def function_errors(label: str, function: ast.FunctionDef) -> list[str]:
    """A public function has a docstring, with a Returns: section when it returns a value."""
    doc = ast.get_docstring(function) or ""
    where = f"{label}:{function.lineno}: {function.name}"
    errors = []
    if not doc.strip():
        errors.append(f"{where} needs a docstring, including short functions")
    if returns_value(function) and "\nReturns:\n" not in "\n" + doc + "\n":
        errors.append(f"{where} needs a Returns: section")
    return errors


def public_api_errors(root: Path, inventory: dict[str, Any]) -> list[str]:
    """
    The public functions of each public entrypoint are documented. This is a syntax check,
    not Starlark evaluation; real exports and attribute schemas are obtained independently
    from Bazel's evaluated extractor.
    """
    functions = (
        (label, node)
        for label in inventory["PUBLIC_APIS"]
        if (path := label_path(root, label)).is_file()
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name[0].isalpha()
    )
    return [error for label, node in functions for error in function_errors(label, node)]


def inventory_errors(root: Path, inventory: dict[str, Any]) -> list[str]:
    return [
        *role_errors(inventory, actual_modules(root)),
        *entrypoint_errors(inventory),
        *visibility_errors(root, inventory),
        *public_api_errors(root, inventory),
    ]


# ==== Bazel ===================================================================


def run_bazel(bazel: str, root: Path, *args: str, capture: bool = False) -> str:
    result = subprocess.run(
        [bazel, *args],
        cwd=root,
        env=nested_tool_environment(os.environ),
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bazel", default=os.environ.get("BAZEL", "bazel"))
    args = parser.parse_args()
    root = Path(os.environ["BUILD_WORKSPACE_DIRECTORY"])
    ruleset = root / RULESET
    inventory = read_inventory(root / INVENTORY)
    errors = inventory_errors(ruleset, inventory)
    if errors:
        sys.exit("\n".join(errors))
    print(
        f"API inventory: {len(inventory['PUBLIC_APIS'])} public entrypoints, "
        f"{len(inventory['CROSS_REPOSITORY_MODULES'])} cross-repository modules excluded from the registry's documentation; all Godot modules classified.",
        flush=True,
    )
    labels = {
        label
        for label in run_bazel(
            args.bazel,
            ruleset,
            "query",
            'attr(visibility, "//visibility:public", kind("rule", //godot/...))',
            "--output=label",
            capture=True,
        ).splitlines()
        if documented_target(label)
    }
    targets = inventory["PUBLIC_TARGETS"]
    if labels != set(targets):
        sys.exit(
            f"Update PUBLIC_TARGETS; undocumented: {sorted(labels - set(targets))}; stale: {sorted(set(targets) - labels)}"
        )
    if any(not description.strip() for description in targets.values()):
        sys.exit("PUBLIC_TARGETS descriptions must be nonempty.")
    run_bazel(args.bazel, root, "test", "//tools/docs/...")
    print("API entrypoints, ownership, internal separation and descriptions passed.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except ValueError as error:
        sys.exit(str(error))
