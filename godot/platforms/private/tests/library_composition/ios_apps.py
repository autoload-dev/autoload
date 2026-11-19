"""Read the iOS applications a library composition test builds."""

import plistlib
import subprocess
from pathlib import Path

from tools.platforms.apple_bundle import application_bundle


def bundle(paths: list[str]) -> Path:
    """
    Return the application among an iOS application's default outputs.

    A Simulator build keeps it an .app directory; a device build archives it as an .ipa.
    """
    (path,) = [Path(path) for path in paths if path.endswith((".app", ".ipa"))]
    return path


def unpacked(paths: list[str], work: Path) -> tuple[Path, dict, Path]:
    """Return the .app directory, its Info.plist and its executable."""
    app = application_bundle(bundle(paths), work)
    info = plistlib.loads((app / "Info.plist").read_bytes())
    return app, info, app / info["CFBundleExecutable"]


def defined_symbols(executable: Path) -> set[str]:
    """
    Return the C names of the symbols the executable defines, local ones included.

    An exported symbols list, such as static extension libraries add, keeps everything else
    out of the exports.
    """
    output = subprocess.run(
        ["/usr/bin/nm", "-U", str(executable)],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout
    return {
        line.split()[-1].removeprefix("_") for line in output.splitlines() if line.strip()
    }
