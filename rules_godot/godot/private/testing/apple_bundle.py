"""
Read an iOS application as rules_apple builds it: an .ipa archive or an .app directory.

Development builds keep the bundle a directory; distribution builds archive it as an .ipa
with the bundle under Payload/. A trimmed copy of the ruleset's build-tool reader, so the
public inspection helper carries its own implementation.
"""

import shutil
import stat
import zipfile
from pathlib import Path


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
