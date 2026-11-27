"""
no-component-names-in-tooling: the repository's Python tooling names no add-on module or
application.
"""

import ast
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from tools.conventions.context import Context, EvidenceError, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.layout import is_application
from tools.setup.modules import is_addon_module

TOOLS = "tools/"


def pattern(names: Iterable[str]) -> re.Pattern[str]:
    """
    A component's name as a word of a string, also inside a flag or a label such as
    `--config=<name>` or `@autoload_<name>//`; a file extension such as `.dart` is none.
    """
    alternatives = "|".join(sorted(map(re.escape, names), key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9.])(?:autoload_)?({alternatives})(?![A-Za-z0-9])")


def components(workspace: Workspace) -> frozenset[str]:
    """The add-on modules and the applications of examples/, by directory."""
    modules = [path.name for path in workspace.module_paths if is_addon_module(path)]
    applications = [path.name for path in workspace.configured if is_application(path)]
    return frozenset({*modules, *applications})


def is_tooling(name: str) -> bool:
    """A Python file of the tools, apart from their tests and test support."""
    path = Path(name)
    return (
        name.startswith(TOOLS)
        and path.suffix == ".py"
        and not path.stem.endswith("_test")
        and path.stem != "test_support"
    )


def strings(name: str, text: str) -> Iterator[tuple[int, str]]:
    """The string literals of a Python source, docstrings included, by line."""
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise EvidenceError(f"{name}: {error}") from error
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


class NoComponentNames:
    info = RuleInfo(
        "no-component-names-in-tooling",
        "The Python tooling names no add-on module or application",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        names = components(workspace)
        words = pattern(names)
        for name in filter(is_tooling, workspace.files):
            text = workspace.text(name)
            # Most tools mention no component at all: parse only those that might.
            if any(component in text for component in names):
                yield from self.named(name, text, words)

    @staticmethod
    def named(name: str, text: str, words: re.Pattern[str]) -> Iterable[Finding]:
        """The components a Python file's string literals name."""
        for line, value in strings(name, text):
            for component in sorted({match[1] for match in words.finditer(value)}):
                yield Finding(
                    Location(name, line),
                    f"names the component {component}; read it from its manifest",
                )
