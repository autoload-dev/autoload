"""Read Godot module dependencies without importing arbitrary config.py code."""

import ast
from collections.abc import Iterable
from pathlib import Path


def module_dependencies(
    root: str | Path, custom_roots: Iterable[str | Path] = ()
) -> dict[str, list[str]]:
    """
    Return the conservative required dependency graph; optional edges stay off.

    A conditional required edge is included conservatively. Dynamic declarations
    fail rather than silently removing a required engine capability.
    """
    configs: dict[str, Path] = {}
    for base in [Path(root) / "modules", *map(Path, custom_roots)]:
        for config in sorted(base.glob("*/config.py")):
            configs[config.parent.name] = config
    result: dict[str, list[str]] = {name: [] for name in configs}
    for name, config in configs.items():
        for call in ast.walk(ast.parse(config.read_text(), filename=str(config))):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                continue
            if call.func.attr != "module_add_dependencies":
                continue
            try:
                values = [ast.literal_eval(arg) for arg in call.args]
                optional = values[2] if len(values) > 2 else False
                for keyword in call.keywords:
                    if keyword.arg == "optional":
                        optional = ast.literal_eval(keyword.value)
                if not optional:
                    # Some upstream modules use a historical alias for the first
                    # argument. The config.py directory is authoritative here.
                    dependencies = values[1]
                    if not isinstance(dependencies, (list, tuple)) or not all(
                        isinstance(dep, str) for dep in dependencies
                    ):
                        raise ValueError("dependencies must be literal strings")
                    result[name].extend(dependencies)
            except (ValueError, TypeError, IndexError) as error:
                raise ValueError(
                    f"Unsupported dependency declaration in {config}:{call.lineno}"
                ) from error
    return result


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
