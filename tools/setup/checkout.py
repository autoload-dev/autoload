"""
A checkout-shaped copy of the modules' files a test declares, for the setup checks.

The setup checks read the checkout's modules by their paths (modules.py). A test that runs
them declares each module's `module_files` as data: the root module's are in its own runfiles,
and those of each module it overrides with a directory of the checkout, the ruleset and the
add-on modules, in that module's repository. This copies each set to its module's directory.

Bazel reaches only the modules the root module declares, so the add-on modules are those of
its generated segment (tools/addons/declarations.py); the registry test modules in bcr/ come
with their module's files.
"""

import ast
import shutil
from collections.abc import Iterator
from pathlib import Path

from python.runfiles import runfiles

from tools.setup.modules import declarations, label_path, literals


def runfile(path: str) -> Path:
    """A file of the runfiles by its runfiles path, such as `_main/MODULE.bazel`."""
    files = runfiles.Create()
    found = files.Rlocation(path) if files is not None else None
    if found is None:
        raise FileNotFoundError(path)
    return Path(found)


def overrides(root: Path) -> Iterator[tuple[str, str]]:
    """
    Each module the root module overrides with a directory, with that directory: from its
    MODULE.bazel and the segments it includes.
    """
    pending = [root / "MODULE.bazel"]
    while pending:
        for declaration in declarations(pending.pop().read_text()):
            if declaration.kind == "include":
                (label,) = map(ast.literal_eval, declaration.arguments)
                pending.append(label_path(root, label))
            elif declaration.kind == "local_path_override":
                values = literals(declaration.keywords)
                yield values["module_name"], values["path"]


def _copy_tree(source: Path, destination: Path) -> None:
    """
    Copy a runfiles tree as plain files, so that a test may change them, without the test's
    virtual environment, whose interpreter is no file of a module.
    """
    shutil.copytree(
        source,
        destination,
        symlinks=False,
        ignore=shutil.ignore_patterns("*.venv"),
        dirs_exist_ok=True,
    )


def copy(destination: Path) -> Path:
    """Copy the declared modules' files to a checkout-shaped tree at destination."""
    _copy_tree(runfile("_main/MODULE.bazel").parent, destination)
    for module, path in overrides(destination):
        try:
            manifest = runfile(f"{module}/MODULE.bazel")
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"the test declares no files of {module}; add @{module}//:module_files to "
                "its data, as MODULE_FILES (tools/setup/module_files.bzl) has them"
            ) from error
        _copy_tree(manifest.parent, destination / path)
    return destination
