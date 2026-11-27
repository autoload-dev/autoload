"""
Where the bytes of a tool's files come from: a file, an archive member or content, and the
deterministic archives of import results and units.

Sections: Originals, Import results.
"""

import contextlib
import io
import os
import shutil
import tarfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import IO

# Where a staged file's bytes came from: a file, an archive member or content.
Original = Path | tuple[Path, tarfile.TarInfo] | bytes


# ==== Originals ===============================================================


def executable(original: Original) -> bool:
    """Whether original is an executable file, such as an extension's crash handler."""
    if isinstance(original, bytes):
        return False
    if isinstance(original, Path):
        return os.access(original, os.X_OK)
    return bool(original[1].mode & 0o111)


def copy_file(source: Path, destination: Path) -> None:
    """Copy source's bytes to destination; an executable source stays executable."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if executable(source):
        destination.chmod(destination.stat().st_mode | 0o111)


@contextlib.contextmanager
def open_original(original: Original) -> Iterator[IO[bytes]]:
    if isinstance(original, bytes):
        yield io.BytesIO(original)
    elif isinstance(original, Path):
        with original.open("rb") as data:
            yield data
    else:
        archive, member = original
        # Unit archives are uncompressed; "r:" skips probing for compression.
        with tarfile.open(archive, "r:") as stream:
            data = stream.extractfile(member)
            if data is None:
                raise ValueError(f"Archive entry {member.name!r} is not a file")
            yield data


def same_content(path: Path, original: Original) -> bool:
    """Whether path still holds the original bytes, compared in chunks."""
    with path.open("rb") as current, open_original(original) as expected:
        while True:
            chunk = current.read(1 << 20)
            if chunk != expected.read(1 << 20):
                return False
            if not chunk:
                return True


def read_original(original: Original) -> bytes:
    """Return the bytes of a staged file's original."""
    with open_original(original) as data:
        return data.read()


def _size(original: Original) -> int:
    if isinstance(original, bytes):
        return len(original)
    if isinstance(original, Path):
        return original.stat().st_size
    return original[1].size


def write_originals(files: Mapping[str, Original], archive: Path) -> None:
    """Archive files by path from where their bytes come, as write_archive does."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as stream:
        for relative in sorted(files):
            info = tarfile.TarInfo(relative)
            info.size, info.mode, info.mtime, info.uid, info.gid = (
                _size(files[relative]),
                0o644,
                0,
                0,
                0,
            )
            with open_original(files[relative]) as data:
                stream.addfile(info, data)


def write_archive(root: Path, paths: list[str], archive: Path) -> None:
    """Archive files deterministically so equal results have equal bytes."""
    write_originals({relative: root / relative for relative in paths}, archive)


# ==== Import results ==========================================================


# An import unit's result: one archive, or nothing when the unit had no file
# that an importer handles.
IMPORT_ARCHIVE = "import.tar"


def tree_files(tree_root: Path) -> list[tuple[str, Path]]:
    return [
        (source.relative_to(tree_root).as_posix(), source)
        for source in sorted(tree_root.rglob("*"))
        if source.is_file()
    ]


def tree_entries(tree_root: Path) -> Sequence[tuple[str, Original]]:
    """List an import result's files, from its archive or its tree, without extracting."""
    archive = tree_root / IMPORT_ARCHIVE
    if not archive.is_file():
        return tree_files(tree_root)
    with tarfile.open(archive, "r:") as stream:
        members = stream.getmembers()
    for member in members:
        if not member.isreg():
            raise ValueError(f"Unexpected archive entry {member.name!r} in {archive}")
    return [(member.name, (archive, member)) for member in members]
