"""RG022: the repository's Python tooling names no add-on module or application."""

import ast
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from tools.conventions.context import Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.layout import EXAMPLES_ROOT
from tools.setup.modules import is_addon_module

TOOLS = "tools/"
# What separates the words of a string, such as the segments of a path or a label.
SEPARATORS = re.compile(r"[\s/:,()\[\]'\"`]+")


def components(workspace: Workspace) -> frozenset[str]:
    """The add-on modules by directory and module name, and the applications of examples/."""
    modules = [path.name for path in workspace.module_paths if is_addon_module(path)]
    applications = [
        path.name for path in workspace.configured if path.parent == EXAMPLES_ROOT
    ]
    return frozenset({*modules, *(f"autoload_{name}" for name in modules), *applications})


def is_tooling(name: str) -> bool:
    """A Python file of the tools, apart from their tests and test support."""
    path = Path(name)
    return (
        name.startswith(TOOLS)
        and path.suffix == ".py"
        and not path.stem.endswith("_test")
        and path.stem != "test_support"
    )


def strings(text: str) -> Iterator[tuple[int, str]]:
    """The string literals of a Python source, docstrings included, by line."""
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


class NoComponentNames:
    info = RuleInfo(
        "RG022",
        "The Python tooling names no add-on module or application",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        names = components(workspace)
        for name in filter(is_tooling, workspace.files):
            for line, value in strings(workspace.text(name)):
                for word in sorted(set(SEPARATORS.split(value)) & names):
                    component = word.removeprefix("autoload_")
                    yield Finding(
                        Location(name, line),
                        f"{name} names the component {component}; read it from its manifest",
                    )
