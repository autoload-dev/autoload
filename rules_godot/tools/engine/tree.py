"""
Prepare an engine's source tree once for all its recipes.

godot_engine_tree extracts and patches one engine's sources; `prepare` then scopes the
build profile in class_db.h, makes the files read-only and prints the tree's digest. The
recipes link the files hard (tree_link.py); read-only files make a write through such a
link fail instead of changing every recipe's sources.

The scoping, here because the tree applies it, lets class_db.h include the build profile
only where GODOT_DECLARES_BUILD_PROFILE is defined; build_profile.py defines it for the
sources that can reach a registration.
"""

import argparse
import hashlib
import os
import stat
from collections.abc import Iterator
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


def entries(directory: str) -> Iterator[os.DirEntry[str]]:
    """Every entry below a directory; symbolic links are entries, never followed."""
    with os.scandir(directory) as listing:
        for entry in listing:
            yield entry
            if entry.is_dir(follow_symlinks=False):
                yield from entries(entry.path)


def _file_digest(path: str) -> str:
    with open(path, "rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def prepare(root: Path) -> str:
    """
    Scope the build profile, make every file read-only and return the tree's digest.

    The digest covers every path and content of the prepared tree, so whatever changes
    it, an archive, a patch or the way they are applied, changes the descriptor its
    recipes read.
    """
    _scope(root)
    contents = []
    for entry in entries(str(root)):
        name = os.path.relpath(entry.path, root)
        if entry.is_symlink():
            contents.append((name, "link:" + os.readlink(entry.path)))
        elif entry.is_file():
            os.chmod(entry.path, entry.stat().st_mode & ~_WRITABLE)
            contents.append((name, _file_digest(entry.path)))
    return hashlib.sha256(repr(sorted(contents)).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    print(prepare(parser.parse_args().root))


if __name__ == "__main__":
    main()
