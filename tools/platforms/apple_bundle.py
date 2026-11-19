"""
Read an iOS application as rules_apple builds it: an .ipa archive or an .app directory.

Development builds keep the bundle a directory; distribution builds archive it
as an .ipa with the bundle under Payload/. Both read as the same members.
"""

import hashlib
import shutil
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path

from tools.digest import digest


def _members(path: Path) -> dict[str, Path]:
    """Return an .app directory's files by their path in an .ipa archive."""
    return {
        f"Payload/{path.name}/{member.relative_to(path).as_posix()}": member
        for member in sorted(path.rglob("*"))
        if member.is_file()
    }


def bundle_files(
    path: Path, selected: Callable[[str], bool] = lambda _: True
) -> dict[str, bytes]:
    """Return the application's selected files by their path in an .ipa archive."""
    if path.is_dir():
        return {
            name: member.read_bytes()
            for name, member in _members(path).items()
            if selected(name)
        }
    with zipfile.ZipFile(path) as archive:
        return {
            name: archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/") and selected(name)
        }


def application_bundle(path: Path, work: Path) -> Path:
    """
    Return a real copy of the application's .app directory in work.

    An .ipa is extracted; its members must stay inside work and must not be
    symbolic links. A directory, which runfiles present as symbolic links, is
    copied with the links resolved, as code signature checks need.
    """
    if path.is_dir():
        return Path(shutil.copytree(path, work / "Payload" / path.name))
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            member = Path(info.filename)
            if (
                member.is_absolute()
                or ".." in member.parts
                or stat.S_ISLNK(info.external_attr >> 16)
            ):
                raise ValueError("Unsafe IPA archive member: " + info.filename)
        archive.extractall(work)
    apps = list((work / "Payload").glob("*.app"))
    if len(apps) != 1:
        raise ValueError(f"Expected one application bundle, found {apps}")
    return apps[0]


def bundle_identity(path: Path) -> tuple[str, int]:
    """Return the SHA-256 and size of an .ipa, or of an .app directory's members."""
    if path.is_file():
        return digest(path), path.stat().st_size
    members = _members(path)
    combined = hashlib.sha256()
    for name, member in members.items():
        combined.update(name.encode() + b"\0" + bytes.fromhex(digest(member)))
    return combined.hexdigest(), sum(member.stat().st_size for member in members.values())
