"""
The runfiles of a program that `bazel run` or `bazel test` starts, the files a project's
imports and initialization generated among them.

Sections: Runfiles, Generated files.
"""

import functools
import os
import sys
from collections.abc import Callable
from pathlib import Path

from python.runfiles import runfiles as bazel_runfiles

from tools.inputs.originals import Original, tree_entries

# ==== Runfiles ================================================================


@functools.cache
def _manifest(path: str) -> bazel_runfiles.Runfiles:
    """A runfiles manifest, read once."""
    return bazel_runfiles.CreateManifestBased(path)


def _in_directories(key: str) -> list[Path]:
    roots = (os.environ.get(variable) for variable in ("RUNFILES_DIR", "TEST_SRCDIR"))
    return [Path(root) / key for root in roots if root]


def _in_manifest(key: str) -> list[Path]:
    manifest = os.environ.get("RUNFILES_MANIFEST_FILE")
    # The key is canonical already: no repository mapping applies.
    found = manifest and _manifest(manifest).Rlocation(key, source_repo="")
    return [Path(found)] if found else []


def _beside_program(key: str) -> list[Path]:
    """A runfile in the .runfiles directory the running program lies in."""
    parents = Path(sys.argv[0]).parents
    return [parent / key for parent in parents if parent.name.endswith(".runfiles")]


def locate(key: str) -> Path:
    """
    The path of the runfile with a runfiles key, such as `_main/pkg/file`: in the runfiles
    directories, the manifest or beside the program.
    """
    candidates = [*_in_directories(key), *_in_manifest(key), *_beside_program(key)]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(f"Runfile {key} was not found")


def runfile_key(short_path: str, workspace: str) -> str:
    """The runfiles key of a Bazel short path; external repositories start with ../."""
    if short_path.startswith("../"):
        return short_path[3:]
    return workspace + "/" + short_path if workspace else short_path


def runfile_locator(workspace: str) -> Callable[[str], Path]:
    """Resolve a Bazel short path of the runfiles of a target in workspace."""

    def runfile(short_path: str) -> Path:
        return locate(runfile_key(short_path, workspace))

    return runfile


# ==== Generated files =========================================================


def _present_trees(keys: list[str], runfile: Callable[[str], Path]) -> list[str]:
    """
    Import results that exist in the runfiles.

    Bazel omits an empty tree artifact from runfiles; an import unit without
    importable files has an empty import result.
    """
    trees = []
    for key in keys:
        try:
            trees.append(str(runfile(key)))
        except FileNotFoundError:
            pass
    return trees


def import_results(
    project: dict, runfile: Callable[[str], Path]
) -> tuple[list[str], list[str]]:
    """
    A project's import results and its initialization, as present tree paths.

    The initialization carries Godot's global caches; staged after the imports, it
    replaces what Godot re-derived from them.
    """
    imports = [
        line
        for line in runfile(project["imports"]).read_text(encoding="utf-8").splitlines()
        if line
    ]
    return (
        _present_trees(imports, runfile),
        _present_trees([project["initialized"]], runfile),
    )


def tree_files_by_path(imports: list[str], initialized: list[str]) -> dict[str, Original]:
    """Import results, then Godot's caches, which replace what they re-derived."""
    generated: dict[str, Original] = {}
    for tree in imports:
        for path, original in tree_entries(Path(tree)):
            generated.setdefault(path, original)
    for tree in initialized:
        generated.update(tree_entries(Path(tree)))
    return generated


def generated_files(project: dict, runfile: Callable[[str], Path]) -> dict[str, Original]:
    """A project's import results, then Godot's caches, by resource path."""
    return tree_files_by_path(*import_results(project, runfile))
