"""Assemble a Godot runtime and an existing pack without invoking the editor."""

import argparse
import dataclasses
import gzip
import io
import json
import os
import plistlib
import shutil
import stat
import struct
import tarfile
from pathlib import Path, PurePosixPath

from tools.platforms.native_symbols import desktop_runtime, native_format
from tools.platforms.zip_archive import write_zip


def relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError(
            "bundle destinations must be non-empty relative POSIX paths: " + value
        )
    return path


def copy_file(source: str | Path, destination: Path, executable: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(0o755 if executable else 0o644)


def _executable(entry: dict) -> bool:
    """
    Whether a manifest entry is installed executable.

    An entry that keeps its mode, such as an extension's crash handler, is executable when
    its source is. Only those entries ask the source: Bazel marks every output it writes
    executable, so the mode of other sources, such as generated descriptors, says nothing.
    """
    return entry.get("executable", False) or (
        entry.get("keep_mode", False) and os.access(entry["source"], os.X_OK)
    )


def _write_tar(root: Path, members: list[Path], archive: str | Path) -> None:
    """Write the members into a gzip-compressed tar archive, keeping only their modes."""
    with (
        open(archive, "wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as output,
    ):
        for path in members:
            name = root.name + "/" + path.relative_to(root).as_posix()
            info = tarfile.TarInfo(name)
            info.mode = stat.S_IMODE(path.stat().st_mode)
            info.mtime = info.uid = info.gid = 0
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                output.addfile(info)
            else:
                data = path.read_bytes()
                info.size = len(data)
                output.addfile(info, io.BytesIO(data))


def archive_tree(root: Path, archive: str | Path, operating_system: str) -> None:
    """Normalize timestamps, ownership, order and modes for reproducible archives."""
    members = sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())
    if operating_system != "macos":
        _write_tar(root, members, archive)
        return
    write_zip(
        archive,
        {
            root.name + "/" + path.relative_to(root).as_posix(): path
            for path in members
            if not path.is_dir()
        },
        mode=None,
    )


def _thinned(
    source: str | Path, cpu: str, operating_system: str, context: str | None
) -> bytes:
    """
    Return the code of the selected CPU of a native file.

    A manifest entry's context names the extension in the error of a file without it.
    """
    try:
        return desktop_runtime(Path(source).read_bytes(), cpu, operating_system)
    except (ValueError, struct.error) as error:
        if context is None:
            raise
        raise ValueError(
            f"{context}: incompatible native library {source}: {error}; "
            "supply a binary for the requested CPU and SDK"
        ) from error


@dataclasses.dataclass(frozen=True)
class _Installer:
    """
    Copies files into the bundle, keeping only the selected CPU of native code.

    Native code must contain that CPU for the operating system; other files, such
    as a launcher script, are copied unchanged. Without a CPU, every file is.
    """

    cpu: str | None
    operating_system: str

    def __call__(
        self,
        source: str | Path,
        destination: Path,
        executable: bool = False,
        context: str | None = None,
    ) -> None:
        if not (self.cpu and native_format(source)):
            copy_file(source, destination, executable)
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            _thinned(source, self.cpu, self.operating_system, context)
        )
        destination.chmod(0o755 if executable else 0o644)


def _macos_contents(args: argparse.Namespace, root: Path, install: _Installer) -> Path:
    """Install the icon, resources and Info.plist of a macOS bundle; return its resources."""
    resources = root / "Contents" / "Resources"
    with open(args.infoplist_base, "rb") as source:
        plist = plistlib.load(source)
    icon = Path(args.icons) / "icon.icns" if args.icons else None
    if icon and icon.is_file():
        plist["CFBundleIconFile"] = "icon.icns"
        install(icon, resources / "icon.icns")
    # Localizations and compiled asset catalogs keep their layout.
    for directory in map(Path, args.resources or []):
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                install(path, resources / path.relative_to(directory))
    (root / "Contents").mkdir(exist_ok=True)
    (root / "Contents" / "Info.plist").write_bytes(plistlib.dumps(plist, sort_keys=True))
    return resources


def _install_manifest(manifest: str, root: Path, install: _Installer) -> None:
    """Install the manifest's entries, such as extension libraries, beside the bundle's files."""
    occupied = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    for entry in json.loads(Path(manifest).read_text()):
        destination = relative_path(entry["destination"])
        destination_key = destination.as_posix()
        if destination_key in occupied:
            raise ValueError("duplicate bundle destination: " + destination_key)
        occupied.add(destination_key)
        install(
            entry["source"], root / destination, _executable(entry), entry.get("context")
        )


def package(args: argparse.Namespace) -> None:
    install = _Installer(args.cpu, args.operating_system)
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    name = args.app_name
    if name in ("", ".", "..") or any(separator in name for separator in "/\\"):
        raise ValueError("app_name must be a filename without separators")
    if args.operating_system == "macos":
        executable = root / "Contents" / "MacOS" / name
        resources = _macos_contents(args, root, install)
    else:
        executable = root / name
        resources = root
    install(args.runtime, executable, executable=True)
    copy_file(args.pack, resources / (name + ".pck"))
    if args.manifest:
        _install_manifest(args.manifest, root, install)
    archive_tree(root, args.archive, args.operating_system)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operating-system", required=True, choices=["linux", "macos"])
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--cpu", choices=["arm32", "arm64", "x86_32", "x86_64", "rv64"])
    parser.add_argument("--pack", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--infoplist-base", help="Generated macOS Info.plist.")
    parser.add_argument("--icons", help="Directory of the icon a pack rendered.")
    parser.add_argument(
        "--resources", action="append", help="Directory to copy into Contents/Resources."
    )
    parser.add_argument("--manifest")
    package(parser.parse_args())


if __name__ == "__main__":
    main()
