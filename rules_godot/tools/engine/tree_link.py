"""
Give a recipe repository its view of its engine's tree: the tree's files, linked hard.

A recipe's repository gets its own directories with the tree's files linked hard into
them. Godot's build scripts resolve paths, so a symbolic link would lead them out of the
recipe; a hard link is the same file under a second name, which costs no space and
outlives the tree's repository. What a configuration creates stays in the recipe's
directories. The engine tree does not run this module, so changing it extracts nothing.
"""

import argparse
import errno
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from .tree import entries
except ImportError:
    from tree import entries

# The tree repository's own files, which a recipe repository writes for itself.
_REPOSITORY_FILES = frozenset(
    {"BUILD", "BUILD.bazel", "REPO.bazel", "WORKSPACE", "WORKSPACE.bazel", "tree.json"}
)

# Linking is a system call per file, about 15,000 for Godot's tree; threads overlap them.
_LINK_THREADS = 8


def _link_file(source: str, target: str) -> None:
    """Link a file hard, or copy it with its mode where the tree lies on another file system."""
    try:
        os.link(source, target)
    except OSError as error:
        if error.errno not in (errno.EXDEV, errno.EPERM, errno.EMLINK):
            raise
        shutil.copy2(source, target)


def link(tree: Path, recipe: Path, path: str = "") -> None:
    """
    Give a recipe repository the tree's files below path, all of them without one.

    Directories are the recipe's own, files hard links to the tree's, and symbolic links
    within the tree stay symbolic links.
    """
    (recipe / path).mkdir(parents=True, exist_ok=True)
    files = []
    for entry in entries(str(tree / path)):
        relative = os.path.relpath(entry.path, tree)
        if relative in _REPOSITORY_FILES:
            continue
        target = os.path.join(recipe, relative)
        if entry.is_symlink():
            os.symlink(os.readlink(entry.path), target)
        elif entry.is_dir():
            os.mkdir(target)
        else:
            files.append((entry.path, target))
    with ThreadPoolExecutor(_LINK_THREADS) as executor:
        list(executor.map(lambda pair: _link_file(*pair), files))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--path", default="", help="The one directory to link.")
    arguments = parser.parse_args()
    link(arguments.tree, arguments.recipe, arguments.path)


if __name__ == "__main__":
    main()
