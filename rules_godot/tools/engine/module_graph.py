"""Read Godot module dependencies without importing arbitrary config.py code."""

import ast
from collections.abc import Iterable
from pathlib import Path
from typing import TypeGuard


def _module_configs(
    root: str | Path, custom_roots: Iterable[str | Path]
) -> dict[str, Path]:
    """Map each module's name to its config.py; a custom module replaces an upstream one."""
    configs: dict[str, Path] = {}
    for base in [Path(root) / "modules", *map(Path, custom_roots)]:
        for config in sorted(base.glob("*/config.py")):
            configs[config.parent.name] = config
    return configs


def _is_dependency_call(node: ast.AST) -> TypeGuard[ast.Call]:
    """Whether node calls a module_add_dependencies method, as config.py files do."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "module_add_dependencies"
    )


def _is_optional(call: ast.Call, values: list[object]) -> bool:
    """Read the optional flag, which a call passes third or as a keyword."""
    optional = values[2] if len(values) > 2 else False
    for keyword in call.keywords:
        if keyword.arg == "optional":
            optional = ast.literal_eval(keyword.value)
    return bool(optional)


def _module_names(value: object) -> list[str]:
    """Return the dependencies' names; fail unless they are a list or tuple of strings."""
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(name, str) for name in value
    ):
        raise ValueError("dependencies must be literal strings")
    return list(value)


def _required_dependencies(call: ast.Call) -> list[str]:
    """Return the dependencies a call declares, or none when it declares them optional."""
    values = [ast.literal_eval(arg) for arg in call.args]
    if _is_optional(call, values):
        return []
    # The first argument is the module's own name, which some upstream modules give in an
    # old form; the recipe names a module after its config.py directory instead.
    return _module_names(values[1])


def _declared_dependencies(config: Path) -> list[str]:
    """Return the required dependencies that a module's config.py declares."""
    dependencies: list[str] = []
    for node in ast.walk(ast.parse(config.read_text(), filename=str(config))):
        if not _is_dependency_call(node):
            continue
        try:
            dependencies.extend(_required_dependencies(node))
        except (ValueError, TypeError, IndexError) as error:
            raise ValueError(
                f"Unsupported dependency declaration in {config}:{node.lineno}"
            ) from error
    return dependencies


def module_dependencies(
    root: str | Path, custom_roots: Iterable[str | Path] = ()
) -> dict[str, list[str]]:
    """
    Map each module to the modules it requires, leaving out optional dependencies.

    A dependency that a config.py declares only under a condition counts as required.
    A declaration that is not a literal fails, rather than silently dropping a module
    the engine needs.
    """
    configs = _module_configs(root, custom_roots)
    return {name: _declared_dependencies(config) for name, config in configs.items()}


def module_closure(
    requested: Iterable[str], graph: dict[str, list[str]], editor: bool = False
) -> list[str]:
    selected: set[str] = set()
    visiting: list[str] = []

    def visit(name: str) -> None:
        if name not in graph:
            raise ValueError(f"Unknown Godot module: {name}")
        if name in visiting:
            raise ValueError(
                "Godot module dependency cycle: " + " -> ".join(visiting + [name])
            )
        if name in selected:
            return
        visiting.append(name)
        for dependency in sorted(graph[name]):
            visit(dependency)
        visiting.pop()
        selected.add(name)

    for name in sorted(
        set(requested) | ({"freetype", "regex", "svg"} if editor else set())
    ):
        visit(name)
    return sorted(selected)
