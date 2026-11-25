"""
The checkout's Bazel modules and what their declaration files say, for the setup checks.

The root module ignores each consumer module nested in the checkout, so `.bazelignore`
names them; it ignores `addons/` as a whole, whose modules are found by their files. Declarations are read with Python's ast, without evaluating Starlark.
"""

import ast
import os
import shlex
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The add-on modules, each a directory below it; the root module holds their examples.
ADDONS = "addons"
# Where the root module keeps each add-on module's example application, examples/addons/<module>/
# (one project, or one per scenario), and its end-to-end tests, e2e/addons/<module>/.
ADDON_EXAMPLES = Path("examples/addons")
ADDON_E2E = Path("e2e/addons")
# The directory of a released module's registry test modules, bcr/<name>/ (RG020), which its
# .bazelignore lists.
BCR = "bcr"
# The add-on generator's self-test module (tools/addons/selftest.py), addons/selftest/ with
# examples/addons/selftest/ while it runs: never released, and none of the add-on modules.
SELFTEST = "selftest"
# The ruleset's directory: its module, and below .bcr/ its registry templates.
RULESET = Path("rules_godot")


def addon_modules(root: Path) -> tuple[str, ...]:
    """
    The add-on modules of `addons/`, each `addons/<name>` with a `MODULE.bazel`, by name,
    but the generator's self-test module.
    """
    return tuple(
        f"{ADDONS}/{path.parent.name}"
        for path in sorted((root / ADDONS).glob("*/MODULE.bazel"))
        if path.parent.name != SELFTEST
    )


def ignored_modules(root: Path, module: str = ".") -> tuple[str, ...]:
    """
    The modules nested in a module: each directory of its `.bazelignore` that holds a
    MODULE.bazel, with the modules nested in those, relative to the repository root.
    """
    ignore = root / module / ".bazelignore"
    nested = (
        (Path(module) / name).as_posix()
        for name in bazelignore_entries(ignore.read_text() if ignore.is_file() else "")
    )
    return tuple(
        found
        for path in nested
        if (root / path / "MODULE.bazel").is_file()
        for found in (path, *ignored_modules(root, path))
    )


def bazelignore_entries(text: str) -> tuple[str, ...]:
    """The directories a `.bazelignore` names, without its blank lines and comments."""
    lines = (line.strip() for line in text.splitlines())
    return tuple(line for line in lines if line and not line.startswith("#"))


def is_addon_module(module: str | Path) -> bool:
    """Whether a module directory is an add-on module, `addons/<module>`."""
    return Path(module).parent == Path(ADDONS)


def is_released(module: str | Path) -> bool:
    """Whether a module has release archives: the ruleset and every add-on module."""
    return Path(module) == RULESET or is_addon_module(module)


def released_modules(modules: Iterable[Path]) -> tuple[Path, ...]:
    """Those of the modules with release archives."""
    return tuple(module for module in modules if is_released(module))


def is_registry_test_module(module: str | Path) -> bool:
    """Whether a module is a registry test module, bcr/<name>/ of a released module (RG020)."""
    return Path(module).parent.name == BCR and is_released(Path(module).parent.parent)


def registry_test_modules(root: Path) -> tuple[str, ...]:
    """
    The registry test modules of the released modules. No lane builds them in place, so
    module_paths leaves them out; the release archive test runs them (RG020).
    """
    return tuple(
        found.parent.relative_to(root).as_posix()
        for module in module_paths(root)
        if is_released(module)
        for found in sorted((root / module / BCR).glob("*/MODULE.bazel"))
    )


def module_paths(root: Path) -> tuple[str, ...]:
    """
    The root module, every module its `.bazelignore` names, with the modules nested in those,
    and each add-on module of `addons/`: the root ignores `addons` as a whole.
    """
    return (".", *ignored_modules(root), *addon_modules(root))


@dataclass(frozen=True)
class Declaration:
    """
    One call of a MODULE.bazel, such as `bazel_dep` or an extension tag.

    `kind` is the called name; an extension tag is `<extension>.<tag>` and a repository
    rule is its rule name, whatever the local variable is called.
    """

    kind: str
    keywords: dict[str, ast.expr]


def _imported(call: ast.expr, function: str) -> str | None:
    match call:
        case ast.Call(
            func=ast.Name(id=name), args=[_, ast.Constant(value=str(imported))]
        ) if name == function:
            return imported
    return None


def declarations(source: str) -> list[Declaration]:
    """Every call of one MODULE.bazel, including those in comprehensions, in source order."""
    tree = ast.parse(source)
    extensions: dict[str, str] = {}
    rules: dict[str, str] = {}
    for statement in tree.body:
        match statement:
            case ast.Assign(targets=[ast.Name(id=variable)], value=value):
                if (extension := _imported(value, "use_extension")) is not None:
                    extensions[variable] = extension
                elif (rule := _imported(value, "use_repo_rule")) is not None:
                    rules[variable] = rule
    calls = sorted(
        (node for node in ast.walk(tree) if isinstance(node, ast.Call)),
        key=lambda node: (node.lineno, node.col_offset),
    )
    found = []
    for call in calls:
        match call.func:
            case ast.Name(id=name):
                kind = rules.get(name, name)
            case ast.Attribute(value=ast.Name(id=proxy), attr=tag) if proxy in extensions:
                kind = f"{extensions[proxy]}.{tag}"
            case _:
                continue
        keywords = {
            keyword.arg: keyword.value
            for keyword in call.keywords
            if keyword.arg is not None
        }
        found.append(Declaration(kind, keywords))
    return found


def literals(keywords: dict[str, ast.expr]) -> dict[str, Any]:
    """The keywords of a declaration whose values are literals; computed ones are left out."""
    values = {}
    for keyword, value in keywords.items():
        try:
            values[keyword] = ast.literal_eval(value)
        except ValueError:
            # A computed value, such as a comprehension's variable.
            continue
    return values


def bazelrc_options(root: Path, module: str) -> Iterator[tuple[str, str]]:
    """
    Each word of a module's `.bazelrc` and the files it imports, with its `file:line`.

    `import` lines are followed, with `%workspace%` as the module directory; `try-import`
    files are optional and untracked, such as `user.bazelrc`, so they are skipped.
    """
    workspace = root / module

    def read(path: Path) -> Iterator[tuple[str, str]]:
        location = Path(os.path.normpath(path.relative_to(root))).as_posix()
        for number, line in enumerate(path.read_text().splitlines(), 1):
            words = shlex.split(line, comments=True)
            if words[:1] == ["import"] and len(words) == 2:
                yield from read(Path(words[1].replace("%workspace%", str(workspace))))
            elif words[:1] != ["try-import"]:
                for word in words:
                    yield f"{location}:{number}", word

    yield from read(workspace / ".bazelrc")
