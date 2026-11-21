"""
The checkout's Bazel modules and what their declaration files say, for the setup checks.

The root module ignores each consumer module nested in the checkout, so `.bazelignore`
names them. Declarations are read with Python's ast, without evaluating Starlark.
"""

import ast
import os
import shlex
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


# The add-on modules, each a directory below it with its examples/ beside its own module.
ADDONS = "addons"


def addon_modules(root: Path) -> tuple[str, ...]:
    """
    The add-on modules of `addons/`, each `addons/<name>` with a `MODULE.bazel`, by name.
    Hidden directories, such as the generator's self-test module, are none of them.
    """
    return tuple(
        f"{ADDONS}/{path.parent.name}"
        for path in sorted((root / ADDONS).glob("*/MODULE.bazel"))
        if not path.parent.name.startswith(".")
    )


def module_paths(root: Path) -> tuple[str, ...]:
    """
    The root module, every directory of its `.bazelignore` that holds a module, and each
    add-on module of `addons/` with its examples: the root ignores `addons` as a whole.
    """
    ignored = (root / ".bazelignore").read_text().splitlines()
    listed = tuple(
        name
        for name in (line.strip() for line in ignored)
        if name and not name.startswith("#") and (root / name / "MODULE.bazel").is_file()
    )
    addons = tuple(
        module
        for addon in addon_modules(root)
        for module in (addon, f"{addon}/examples")
        if (root / module / "MODULE.bazel").is_file()
    )
    return (".",) + listed + addons


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
