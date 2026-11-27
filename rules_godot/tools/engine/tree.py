"""
Prepare a source archive's tree once for every recipe of every engine that builds from it.

godot_engine_tree extracts the archive and adds SCons; `prepare` then makes the files
read-only and prints the tree's digest. The tree holds nothing one engine's recipes
change, so engines of one source share it. The recipes link its files hard and own
copies of those they change (tree_link.py); read-only files make a write through a link
fail instead of changing every recipe's sources.
"""

import argparse
import hashlib
import os
import stat
from collections.abc import Iterator
from pathlib import Path

_WRITABLE = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


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
    Make every file read-only and return the tree's digest.

    The digest covers every path and content of the tree, so whatever changes it, an
    archive or the way it is extracted, changes the descriptor its recipes read.
    """
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
