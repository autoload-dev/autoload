"""
release-archives-without-tests: the released modules' archives leave out their tests, and
nothing else needs them.
"""

import ast
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath

from tools.conventions.context import Context, Location, Workspace
from tools.conventions.framework import Finding, RuleInfo
from tools.setup.modules import released_modules

# The lines of a released module's .gitattributes that leave every tests/ directory, at any
# depth, out of its release archive (.github/workflows/release_prep.sh), but those of its
# registry test modules in bcr/, which the registry runs from the archive
# (registry-test-module-in-bcr).
EXCLUSIONS = (
    ("tests export-ignore", "the release archive must leave out the module's tests"),
    (
        "bcr/**/tests -export-ignore",
        "the release archive must keep the tests of the registry test modules",
    ),
)
TESTS = "tests"
STARLARK = ("BUILD", "BUILD.bazel", "MODULE.bazel")
# Arguments whose labels name packages without loading them.
VISIBILITY = frozenset({"visibility", "default_visibility", "packages"})


def _outside_tests(name: str) -> bool:
    """Whether a file is Starlark outside every tests/ directory."""
    path = PurePosixPath(name)
    starlark = path.name in STARLARK or path.suffix == ".bzl"
    return starlark and TESTS not in path.parts


def in_tests(value: str) -> bool:
    """Whether a label or relative path names something inside a tests/ directory."""
    if " " in value or "/" not in value:
        return False
    path = value.split("//", 1)[1].split(":", 1)[0] if "//" in value else value
    return TESTS in PurePosixPath(path).parts


def _name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _name(node.value)
    return None


def _dev(call: ast.Call) -> bool:
    return any(
        keyword.arg == "dev_dependency"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )


def _dev_proxies(tree: ast.Module) -> frozenset[str]:
    """The names a MODULE.bazel binds to dev-only extensions and repository rules."""
    return frozenset(
        target.id
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        and isinstance(statement.value, ast.Call)
        and _dev(statement.value)
        for target in statement.targets
        if isinstance(target, ast.Name)
    )


def _hidden(call: ast.Call, dev: frozenset[str]) -> bool:
    """Whether no build of another module loads a call's arguments."""
    callee = _name(call.func)
    return _dev(call) or callee in dev or callee == "visibility"


def _docstring(node: ast.AST) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)


def _loaded_children(node: ast.AST) -> Iterator[ast.AST]:
    """
    A node's children that may be loaded: not visibility arguments, not a glob's excludes,
    which may name what the archive leaves out, and not docstrings.
    """
    if isinstance(node, ast.Call):
        skipped = VISIBILITY | ({"exclude"} if _name(node.func) == "glob" else set())
        yield from node.args
        yield from (k.value for k in node.keywords if k.arg not in skipped)
    elif not _docstring(node):
        yield from ast.iter_child_nodes(node)


def _loaded_strings(node: ast.AST, dev: frozenset[str]) -> Iterator[ast.Constant]:
    """
    The string literals that a build of another module may load: not those that only name
    visibility, nor those of dev dependencies, which only the module's own builds evaluate.
    """
    if isinstance(node, ast.Call) and _hidden(node, dev):
        return
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node
        return
    for child in _loaded_children(node):
        yield from _loaded_strings(child, dev)


def references(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """The lines and values of the strings in Starlark that name something in tests/."""
    dev = _dev_proxies(tree)
    for constant in _loaded_strings(tree, dev):
        value = constant.value
        if isinstance(value, str) and in_tests(value):
            yield constant.lineno, value


class ReleasedWithoutTests:
    info = RuleInfo(
        "release-archives-without-tests",
        "Release archives leave out tests, and nothing else needs them",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        released = released_modules(workspace.module_paths)
        for module in released:
            yield from self.archive(workspace, module)
        for name in filter(_outside_tests, workspace.files):
            if workspace.owner(name) in released:
                yield from self.uses(workspace, name)

    @staticmethod
    def archive(workspace: Workspace, module: Path) -> Iterable[Finding]:
        path = (module / ".gitattributes").as_posix()
        lines = (workspace.text(path) if path in workspace.file_set else "").splitlines()
        for line, message in EXCLUSIONS:
            if line not in lines:
                yield Finding(Location(path, 1), f"{message}: {line}")

    @staticmethod
    def uses(workspace: Workspace, name: str) -> Iterable[Finding]:
        for line, value in references(workspace.syntax(name)):
            yield Finding(
                Location(name, line),
                f"{value} is in a tests/ directory, which the release archive leaves out; "
                "move what uses it into that tests/ package",
            )
