"""
Give a recipe the parts of its custom modules that shape its build graph.

A recipe configures its custom modules from every file but their code, and from the
code's paths: Godot's build scripts, shader sources and data such as documentation can
change the graph by their contents, C and C++ sources and headers only by their names.
`prepare` copies the files that are no code below _custom_modules, lists the code in
_custom_modules.json and writes an empty placeholder of each code file, so SCons finds the
same files; the repository rule watches what it copies and the directory listings, and
deletes the placeholders after the configuration. The code's contents come from the
workspace at build time, by label (godot_custom_module), so editing it recompiles it
without configuring the recipe again. A pin action writes the same placeholders from the
manifest (pin.py).

Sections: Code, Manifest, Preparation.

A recipe's pin covers this module, since the configured graph depends on it.
"""

import argparse
import json
import os
import shutil
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from tools.engine.source_tree import HEADER_SUFFIXES, SOURCE_SUFFIXES

DIRECTORY = "_custom_modules"
MANIFEST = "_custom_modules.json"

# ==== Code ====================================================================


# A module's code: what compiles and what it includes, which shapes the graph by name only.
_CODE_SUFFIXES = frozenset({*SOURCE_SUFFIXES, *HEADER_SUFFIXES})


def is_code(path: Path) -> bool:
    """Whether a custom module file is code, whose contents come by label at build time."""
    return path.suffix in _CODE_SUFFIXES


def shapes_graph(path: Path) -> bool:
    """
    Whether a custom module file's contents can change the configured graph.

    Godot's build scripts decide which files compile and how, and a script may read any
    other file of the module, so every file's contents count but the code's: a source or
    header counts only by its path, so editing a module's code keeps its pin.
    """
    return not is_code(path)


# ==== Manifest ================================================================


def read_manifest(root: Path) -> dict[str, Any]:
    """The custom modules a recipe lists: each one's label and other files; none without."""
    path = root / MANIFEST
    return json.loads(path.read_text()) if path.is_file() else {}


def code_files(root: Path) -> list[str]:
    """The paths below the source root of the module files whose contents come by label."""
    return [
        f"{DIRECTORY}/{name}/{path}"
        for name, module in sorted(read_manifest(root).items())
        for path in module["files"]
    ]


def write_placeholders(root: Path) -> list[str]:
    """Write an empty file at each listed path without one and return those paths."""
    written = []
    for name in code_files(root):
        path = root / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            written.append(name)
    return written


# ==== Preparation =============================================================


# Bazel's files and caches of a module's directory, which are no part of the module.
_IGNORED = frozenset({".git", "__pycache__", "BUILD", "BUILD.bazel"})


class Module(NamedTuple):
    """A custom module: its name, its directory in the workspace and its files' target."""

    name: str
    directory: Path
    label: str


def parse_module(name: str, directory: str, label: str) -> Module:
    """A module from its name, its directory and its files' target."""
    if not name.replace("_", "").isalnum() or name[0].isdigit():
        raise ValueError(f"Invalid custom module name: {name}")
    return Module(name, Path(directory), label)


def _walk(directory: Path) -> Iterable[tuple[str, list[str]]]:
    """Each directory below a module's, relative to it, with its files; Bazel's left out."""
    for current, directories, names in os.walk(directory):
        directories[:] = sorted(name for name in directories if name not in _IGNORED)
        relative = os.path.relpath(current, directory)
        yield relative, sorted(name for name in names if name not in _IGNORED)


def _module_files(module: Module) -> tuple[list[str], list[str]]:
    """A module's directories and files below its own, relative to it."""
    directories = []
    files = []
    for relative, names in _walk(module.directory):
        directories.append(relative)
        files.extend(os.path.normpath(os.path.join(relative, name)) for name in names)
    return directories, sorted(files)


def _copy(recipe: Path, module: Module, paths: Iterable[str]) -> None:
    """Copy a module's files to the same paths below the recipe's _custom_modules."""
    for path in paths:
        target = recipe / DIRECTORY / module.name / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(module.directory / path, target)


def prepare(recipe: Path, modules: Sequence[Module]) -> dict[str, Any]:
    """
    Copy what shapes each module's graph, list its code and write the code's placeholders.

    Return what the repository rule watches, each module's directories and graph files
    relative to the module, and the placeholders it deletes after the configuration.
    """
    manifest: dict[str, Any] = {}
    watched: dict[str, Any] = {}
    for module in modules:
        directories, files = _module_files(module)
        graph = [path for path in files if shapes_graph(Path(path))]
        _copy(recipe, module, graph)
        code = [path for path in files if not shapes_graph(Path(path))]
        manifest[module.name] = {"label": module.label, "files": code}
        watched[module.name] = {"directories": directories, "files": graph}
    (recipe / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"modules": watched, "placeholders": write_placeholders(recipe)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument(
        "--module",
        nargs=3,
        action="append",
        default=[],
        metavar=("NAME", "DIRECTORY", "LABEL"),
    )
    arguments = parser.parse_args()
    modules = [parse_module(*declaration) for declaration in arguments.module]
    print(json.dumps(prepare(arguments.recipe, modules)))


if __name__ == "__main__":
    main()
