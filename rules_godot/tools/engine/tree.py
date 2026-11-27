"""
Prepare an engine's source tree once, and give each recipe repository its view of it.

godot_engine_tree extracts and patches one engine's sources; `prepare` then scopes the
build profile in class_db.h and makes the files read-only. A recipe runs `link`: its
repository gets its own directories with the tree's files linked hard into them. Godot's
build scripts resolve paths, so a symbolic link would lead them out of the recipe; a hard
link is the same file under a second name, which costs no space and outlives the tree's
repository. Read-only files make a write through such a link fail instead of changing every
recipe's sources; what a configuration creates stays in the recipe's directories.

The scoping, here because the tree applies it, lets class_db.h include the build profile
only where GODOT_DECLARES_BUILD_PROFILE is defined; build_profile.py defines it for the
sources that can reach a registration.
"""

import argparse
import errno
import os
import shutil
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HEADER = "core/disabled_classes.gen.h"
DEFINE = "GODOT_DECLARES_BUILD_PROFILE"
CLASS_DB = "core/object/class_db.h"

_UPSTREAM = f"""\
#define GD_IS_CLASS_ENABLED(m_class) is_class_enabled_v<m_class>

#include "{HEADER}" // IWYU pragma: keep.
"""

_SCOPED = f"""\
// rules_godot gives the build profile only to the sources that register classes, so a
// profile change recompiles those alone (tools/engine/build_profile.py).
#ifdef {DEFINE}
#define GD_IS_CLASS_ENABLED(m_class) is_class_enabled_v<m_class>
#include "{HEADER}" // IWYU pragma: keep.
#else
#define GD_IS_CLASS_ENABLED(m_class) GODOT_BUILD_PROFILE_NOT_DECLARED_FOR_##m_class
#endif
"""

# The tree repository's own files, which a recipe repository writes for itself.
_REPOSITORY_FILES = frozenset(
    {"BUILD", "BUILD.bazel", "REPO.bazel", "WORKSPACE", "WORKSPACE.bazel", "tree.json"}
)

_WRITABLE = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


def _scope(root: Path) -> None:
    """Rewrite upstream's class_db.h to include the build profile only where it is declared."""
    path = root / CLASS_DB
    text = path.read_text() if path.is_file() else ""
    if text.count(_UPSTREAM) == 1:
        path.write_text(text.replace(_UPSTREAM, _SCOPED))


def is_scoped(root: Path) -> bool:
    """
    Return whether the tree's class_db.h includes the build profile only where declared.

    A fork that changed upstream's include keeps it, and every source the profile.
    """
    path = root / CLASS_DB
    return path.is_file() and path.read_text().count(_SCOPED) == 1


def prepare(root: Path) -> None:
    """Scope the build profile and make every file of the extracted, patched tree read-only."""
    _scope(root)
    for directory, _directories, names in os.walk(root):
        for name in names:
            path = Path(directory) / name
            if not path.is_symlink():
                path.chmod(path.stat().st_mode & ~_WRITABLE)


def _link_file(source: Path, target: Path) -> None:
    """Link a file hard, or copy it where the tree lies on another file system."""
    try:
        os.link(source, target)
    except OSError as error:
        if error.errno not in (errno.EXDEV, errno.EPERM, errno.EMLINK):
            raise
        shutil.copyfile(source, target)


# Linking is a system call per file, about 15,000 for Godot's tree; threads overlap them.
_LINK_THREADS = 8


def link(tree: Path, recipe: Path, path: str = "") -> None:
    """
    Give a recipe repository the tree's files below path, all of them without one.

    Directories are the recipe's own, files hard links to the tree's, and symbolic links
    within the tree stay symbolic links.
    """
    files = []
    for directory, directories, names in os.walk(tree / path if path else tree):
        current = Path(directory)
        target = recipe / current.relative_to(tree)
        target.mkdir(parents=True, exist_ok=True)
        if current == tree:
            names = [name for name in names if name not in _REPOSITORY_FILES]
        for name in [
            *names,
            *(name for name in directories if (current / name).is_symlink()),
        ]:
            if (current / name).is_symlink():
                (target / name).symlink_to(os.readlink(current / name))
            else:
                files.append((current / name, target / name))
    with ThreadPoolExecutor(_LINK_THREADS) as executor:
        list(executor.map(lambda pair: _link_file(*pair), files))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare").add_argument("--root", type=Path, required=True)
    linking = commands.add_parser("link")
    linking.add_argument("--tree", type=Path, required=True)
    linking.add_argument("--recipe", type=Path, required=True)
    linking.add_argument("--path", default="", help="The one directory to link.")
    arguments = parser.parse_args()
    if arguments.command == "prepare":
        prepare(arguments.root)
    else:
        link(arguments.tree, arguments.recipe, arguments.path)


if __name__ == "__main__":
    main()
