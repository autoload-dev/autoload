"""
Godot's rules for the files it writes beside a resource and the directories it ignores.

Godot's editor file system writes `<path>.import` for an imported file and
`<path>.uid` for a script, shader or other file with a UID, and never treats a
file with either suffix, in any case, as a resource of its own. Build tools apply the rule
here to files Godot wrote inside an action and to files that sit in a checkout
before they are declared.

Godot-ignored files are those Godot's editor file system never scans, so Godot never
imports or registers them, while code still reads them through FileAccess when Godot runs
from the sources. Godot 4.7.2 has one rule for them, which `godot_ignored` in
godot/private/paths.bzl applies to declared files and the tools that walk a checkout apply
with DIRECTORY_MARKERS and is_hidden:

- `EditorFileSystem::_should_skip_directory` (editor/file_system/editor_file_system.cpp)
  skips the project data directory (`.godot`), a directory holding a `project.godot`
  (another project) and one holding a `.gdignore`, each with everything below it; the
  scan and the export's include filter both call it, and it never applies to the
  project's root directory.
- `EditorFileSystem::_scan_new_dir` skips hidden files and directories
  (`current_is_hidden`), on Unix those whose names begin with a dot
  (`DirAccessUnix::is_hidden`, drivers/unix/dir_access_unix.cpp). The export's include
  filter (`EditorExportPlatform::_edit_files_with_filter`) skips such directories, while
  it still packs a hidden file in a visible directory.
"""

import hashlib
from collections.abc import Collection
from pathlib import PurePosixPath

# The files Godot writes beside a file: its import settings and its UID.
IMPORT = ".import"
UID = ".uid"
SIDECAR_SUFFIXES = (IMPORT, UID)
# What an export writes in place of a resource it converted.
REMAP = ".remap"
# The files that make Godot skip their directory.
DIRECTORY_MARKERS = (".gdignore", "project.godot")
# The project data file that lists the extensions Godot loads when the runtime starts.
EXTENSION_LIST = ".godot/extension_list.cfg"


def is_sidecar_named(path: str) -> bool:
    """Whether Godot treats the path as metadata, never as a resource."""
    return path.lower().endswith(SIDECAR_SUFFIXES)


def sidecar_source(path: str) -> str | None:
    """The file whose sidecar the path is, or None for any other path."""
    if not is_sidecar_named(path):
        return None
    source = path.rpartition(".")[0]
    if not source.rpartition("/")[2] or is_sidecar_named(source):
        return None
    return source


def is_uid_sidecar(path: str) -> bool:
    """Whether the path is the UID sidecar of a file."""
    return path.lower().endswith(UID) and sidecar_source(path) is not None


def sidecars_of(path: str) -> tuple[str, ...]:
    """The sidecars Godot may write for the file, none for a sidecar-named path."""
    if is_sidecar_named(path):
        return ()
    return tuple(path + suffix for suffix in SIDECAR_SUFFIXES)


def is_hidden(path: str) -> bool:
    """Whether a file or one of its directories is hidden from Godot: its name begins with a dot."""
    return any(part.startswith(".") for part in path.split("/"))


def hidden_by(path: str, paths: Collection[str]) -> str | None:
    """
    What makes Godot's export leave out a file: a hidden directory, or a marker among paths.

    The export's include filter skips hidden directories and those holding a marker, and
    packs every other file, a hidden file of a visible directory too, for which this
    returns None. The result is the hidden directory or the marker file, such as
    `report/.gdignore`.
    """
    directories = path.split("/")[:-1]
    for depth in range(1, len(directories) + 1):
        directory = "/".join(directories[:depth])
        if is_hidden(directory):
            return directory
        for marker in DIRECTORY_MARKERS:
            if f"{directory}/{marker}" in paths:
                return f"{directory}/{marker}"
    return None


def import_base(path: str) -> str:
    """
    The start of the names of the files Godot's import of a resource path writes.

    Godot names them after the file and the MD5 of its res:// path, such as
    .godot/imported/icon.svg-<md5>.ctex and .godot/imported/icon.svg-<md5>.md5.
    """
    name = PurePosixPath(path).name
    digest = hashlib.md5(("res://" + path).encode("utf-8")).hexdigest()
    return f".godot/imported/{name}-{digest}."
