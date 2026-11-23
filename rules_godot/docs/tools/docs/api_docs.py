"""Discover every source module, then check the API inventory and its documentation."""

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.conventions.environment import nested_tool_environment

ROLES = (
    "PUBLIC_APIS",
    "CROSS_REPOSITORY_MODULES",
    "SUPPORT_MODULES",
)


def module_label(path: Path) -> str:
    return f"//{path.parent.as_posix()}:{path.name}"


def module_path(root: Path, label: str) -> Path:
    return root / label.removeprefix("//").replace(":", "/")


def package(label: str) -> str:
    return label.removeprefix("//").split(":")[0]


def is_private(label: str) -> bool:
    return "private" in package(label).split("/")


def is_white_box_test(label: str) -> bool:
    return "tests" in package(label).split("/")


def documented_target(label: str) -> bool:
    """Whether a public rule target under //godot belongs in PUBLIC_TARGETS."""
    return not (is_private(label) or is_white_box_test(label))


def read_inventory(manifest: Path) -> dict[str, Any]:
    tree = ast.parse(manifest.read_text())
    return {
        target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(target := node.targets[0], ast.Name)
    }


def inventory_errors(root: Path, inventory: dict[str, Any]) -> list[str]:
    errors = []
    # White-box tests in tests/ subpackages load private files but are no API modules.
    actual = {
        label
        for path in (root / "godot").rglob("*.bzl")
        if not is_white_box_test(label := module_label(path.relative_to(root)))
    }
    declared: dict[str, str] = {}
    # The other roles are dicts, so only this list can repeat a module.
    if len(inventory["SUPPORT_MODULES"]) != len(set(inventory["SUPPORT_MODULES"])):
        errors.append("SUPPORT_MODULES: duplicate modules")
    for role in ROLES:
        for label in inventory[role]:
            if label in declared:
                errors.append(
                    f"{label}: multiple module roles ({declared[label]}, {role})"
                )
            declared[label] = role
            if label not in actual:
                errors.append(f"{role}: stale module {label}")
            if role == "SUPPORT_MODULES" and not is_private(label):
                errors.append(
                    f"{label}: support modules must be private implementation files; classify loadable contracts explicitly"
                )
    for label in sorted(actual - set(declared)):
        errors.append(
            f"{label}: unclassified new module; declare its API role in docs/public/api/modules.bzl"
        )
    for label, symbols in inventory["PUBLIC_APIS"].items():
        if not symbols:
            errors.append(f"{label}: public entrypoints need primary symbols")
    for label, purpose in inventory["CROSS_REPOSITORY_MODULES"].items():
        if not purpose.strip():
            errors.append(
                f"{label}: cross-repository modules need a cross-repository load explanation"
            )
    for label in list(inventory["SUPPORT_MODULES"]) + list(
        inventory["CROSS_REPOSITORY_MODULES"]
    ):
        path = module_path(root, label)
        if not path.is_file():
            continue
        calls = [
            node.value
            for node in ast.parse(path.read_text()).body
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "visibility"
        ]
        cross_repository = label in inventory["CROSS_REPOSITORY_MODULES"]
        specs = [ast.literal_eval(call.args[0]) for call in calls]
        public = any(
            spec == "public" or isinstance(spec, list) and "public" in spec
            for spec in specs
        )
        if not calls and not cross_repository:
            errors.append(
                f"{label}: support modules need explicit restricted load visibility"
            )
        if cross_repository and not public:
            errors.append(
                f"{label}: cross-repository modules need explicit public load visibility"
            )
        elif not cross_repository and public:
            errors.append(f"{label}: support modules cannot have public load visibility")
    # This is a syntax check, not Starlark evaluation. Real exports and
    # attribute schemas are obtained independently from Bazel's evaluated extractor.
    for label in inventory["PUBLIC_APIS"]:
        path = module_path(root, label)
        if not path.is_file():
            continue
        for node in ast.parse(path.read_text()).body:
            if not isinstance(node, ast.FunctionDef) or not node.name[0].isalpha():
                continue
            doc = ast.get_docstring(node) or ""
            if not doc.strip():
                errors.append(
                    f"{label}:{node.lineno}: {node.name} needs a docstring, including short functions"
                )
            returns_value = any(
                isinstance(child, ast.Return) and child.value is not None
                for child in ast.walk(node)
            )
            if returns_value and "\nReturns:\n" not in "\n" + doc + "\n":
                errors.append(
                    f"{label}:{node.lineno}: {node.name} needs a Returns: section"
                )
    return errors


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
    ruleset = root.parent
    inventory = read_inventory(root / "public/api/modules.bzl")
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
    run_bazel(args.bazel, root, "test", "//...")
    print("API entrypoints, ownership, internal separation and descriptions passed.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except ValueError as error:
        sys.exit(str(error))
