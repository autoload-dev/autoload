"""
Give a recipe repository its view of its source's tree: the tree's files, linked hard, and
its own copies of the files it changes.

A recipe's repository gets its own directories with the tree's files linked hard into
them. Godot's build scripts resolve paths, so a symbolic link would lead them out of the
recipe; a hard link is the same file under a second name, which costs no space and
outlives the tree's repository. The engine tree is the source archive's and shared by
every engine of that source, so a recipe changes no linked file: for exactly the files
its patches touch, and for class_db.h, which it scopes (class_db.py), it holds a copy of
its own. What a configuration creates stays in the recipe's directories. The engine tree
does not run this module, so changing it extracts nothing.

Sections: Links, Recipe view.
"""

import argparse
import errno
import os
import shutil
import stat
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from . import class_db
    from .patches import Patches, apply_patches, touched
    from .tree import entries
except ImportError:
    import class_db  # type: ignore[no-redef]
    from patches import Patches, apply_patches, touched  # type: ignore[no-redef]
    from tree import entries  # type: ignore[no-redef]

# ==== Links ===================================================================


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


def own(tree: Path, recipe: Path, names: Iterable[str]) -> None:
    """
    Replace the recipe's links of the named files with writable copies of the tree's.

    A name the tree lacks, such as a file a patch adds, stays absent.
    """
    for name in names:
        source = tree / name
        if not source.is_file() or source.is_symlink():
            continue
        target = recipe / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        shutil.copy2(source, target)
        target.chmod(target.stat().st_mode | stat.S_IWUSR)


# ==== Recipe view =============================================================

# A recipe without patches.
NO_PATCHES = Patches()


def prepare(
    tree: Path, recipe: Path, path: str = "", patches: Patches = NO_PATCHES
) -> None:
    """
    Link the tree's files below path into a recipe, patch its copies and scope class_db.h.

    The recipe owns the files its patches touch, so the patches apply to upstream's
    text, then class_db.h, if the recipe has it, which it scopes after them.
    """
    link(tree, recipe, path)
    names = {
        name
        for patch in patches.files
        for name in touched(Path(patch).read_text(), patches.strip)
    }
    if (recipe / class_db.CLASS_DB).is_file():
        names.add(class_db.CLASS_DB)
    own(tree, recipe, names)
    apply_patches(recipe, patches.files, patches.strip)
    class_db.scope(recipe)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--path", default="", help="The one directory to link.")
    parser.add_argument("--patch", type=Path, action="append", default=[])
    parser.add_argument("--patch-strip", type=int, default=1)
    arguments = parser.parse_args()
    patches = Patches(arguments.patch, arguments.patch_strip)
    prepare(arguments.tree, arguments.recipe, arguments.path, patches)


if __name__ == "__main__":
    main()
