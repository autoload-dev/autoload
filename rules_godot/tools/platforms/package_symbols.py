"""Collect unstripped native code and .dSYM bundles into a reproducible ZIP."""

import argparse
import json
from pathlib import Path

from tools.platforms.native_symbols import native_format
from tools.platforms.package_desktop import relative_path
from tools.platforms.zip_archive import write_zip


def package(output: str | Path, manifest: list[dict[str, str]]) -> None:
    files: dict[str, Path] = {}
    for entry in manifest:
        destination = relative_path(entry["destination"])
        source = Path(entry["source"])
        if source.is_dir():
            # A .dSYM is a directory; its files keep their layout below its path.
            members = [
                (destination / path.relative_to(source).as_posix(), path)
                for path in source.rglob("*")
                if path.is_file()
            ]
        elif native_format(source):
            members = [(destination, source)]
        else:
            # Launcher scripts and other files a runtime may be carry no symbols.
            members = []
        for name, path in members:
            if name.as_posix() in files:
                raise ValueError("duplicate symbol path: " + name.as_posix())
            files[name.as_posix()] = path
    write_zip(output, files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", required=True, help="JSON destinations and sources."
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    package(args.output, json.loads(Path(args.manifest).read_text()))


if __name__ == "__main__":
    main()
