"""
definitions-before-callers: in Python, a module's function or class stands before its
first caller.
"""

import ast
from collections.abc import Iterable, Iterator, Mapping
from pathlib import PurePosixPath

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.python_modules import parse

DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
type Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def local_names(definition: Definition) -> set[str]:
    """The names a definition binds itself: parameters and assigned names."""
    return {
        node.arg if isinstance(node, ast.arg) else node.id
        for node in ast.walk(definition)
        if isinstance(node, ast.arg)
        or (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store))
    }


def callers_of(definitions: Mapping[str, Definition]) -> dict[str, set[str]]:
    """The module's other definitions that name each definition, not a local of its name."""
    callers: dict[str, set[str]] = {name: set() for name in definitions}
    for caller, definition in definitions.items():
        named = {n.id for n in ast.walk(definition) if isinstance(n, ast.Name)}
        for name in (named - local_names(definition)) & callers.keys() - {caller}:
            callers[name].add(caller)
    return callers


def reaches(callers: Mapping[str, set[str]], start: str, goal: str) -> bool:
    """Whether goal names start, directly or through other definitions."""
    seen, stack = {start}, [start]
    while stack:
        for name in callers[stack.pop()]:
            if name == goal:
                return True
            if name not in seen:
                seen.add(name)
                stack.append(name)
    return False


def late_definitions(module: ast.Module) -> Iterator[tuple[Definition, Definition]]:
    """Each definition that stands below its first caller, with that caller."""
    definitions = {
        statement.name: statement
        for statement in module.body
        if isinstance(statement, DEFINITIONS)
    }
    callers = callers_of(definitions)
    for name, definition in definitions.items():
        above = sorted(
            (definitions[caller] for caller in callers[name]),
            key=lambda caller: caller.lineno,
        )
        for caller in above:
            if caller.lineno > definition.lineno:
                break
            # Recursion between definitions leaves one of them below its caller.
            if not reaches(callers, caller.name, name):
                yield definition, caller
                break


class ReadingOrder:
    info = RuleInfo(
        "definitions-before-callers", "Python definitions stand before their first caller"
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        for name in workspace.files:
            if PurePosixPath(name).suffix != ".py":
                continue
            for definition, caller in late_definitions(parse(workspace, name)):
                yield Finding(
                    Location(name, definition.lineno),
                    f"move {definition.name} above its first caller, "
                    f"{caller.name} on line {caller.lineno}",
                )
