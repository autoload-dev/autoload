"""Read the Godot sources the repository pins and the engine profiles of their minors."""

import json
import os
import tarfile
from pathlib import Path

RUNFILES = Path(os.environ["TEST_SRCDIR"])
WORKSPACE = RUNFILES / os.environ["TEST_WORKSPACE"]


def version(source: Path) -> str:
    """The Godot version of a pinned source, such as 4.7.2."""
    return json.loads(source.read_text())["version"]


def minor(source: Path) -> str:
    """The Godot minor of a pinned source, such as 4.7."""
    return ".".join(version(source).split(".")[:2])


def files(source: Path, paths: set[str]) -> dict[str, bytes]:
    """Read files of a pinned source archive by their path below its root."""
    meta = json.loads(source.read_text())
    prefix = meta["strip_prefix"] + "/"
    found = {}
    with tarfile.open(source.parent / meta["archive"], "r|*") as archive:
        for member in archive:
            path = member.name.removeprefix(prefix)
            if path in paths:
                stream = archive.extractfile(member)
                assert stream is not None
                found[path] = stream.read()
                if len(found) == len(paths):
                    break
    return found


def profile(godot_minor: str) -> dict:
    """The engine profile of a Godot minor, as the package's profile_* targets write it."""
    name = "profile_" + godot_minor.replace(".", "_") + ".json"
    return json.loads((WORKSPACE / "godot/private/engine/tests" / name).read_text())
