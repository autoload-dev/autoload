"""Write ZIP archives whose bytes depend only on their members."""

import shutil
import stat
import zipfile
from collections.abc import Mapping
from pathlib import Path


def write_zip(
    output: str | Path, members: Mapping[str, bytes | Path], mode: int | None = 0o644
) -> None:
    """
    Write members in name order with a fixed date and Unix file modes.

    Args:
        output: The ZIP file to write.
        members: Archive names to contents, or to files whose contents are
            streamed, such as unstripped libraries of hundreds of megabytes.
        mode: Permission bits of every member; None keeps each file's own.
    """
    with zipfile.ZipFile(output, "w") as archive:
        for name, source in sorted(members.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.compress_type = zipfile.ZIP_DEFLATED
            if isinstance(source, bytes):
                entry.external_attr = (stat.S_IFREG | (mode or 0o644)) << 16
                archive.writestr(entry, source)
                continue
            status = source.stat()
            permissions = stat.S_IMODE(status.st_mode) if mode is None else mode
            entry.external_attr = (stat.S_IFREG | permissions) << 16
            entry.file_size = status.st_size
            with source.open("rb") as data, archive.open(entry, "w") as destination:
                shutil.copyfileobj(data, destination, 1 << 20)
