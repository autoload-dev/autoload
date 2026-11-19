"""
Compile a Liquid Glass .icon of Icon Composer with actool, as Godot's macOS export does.

The project's files of the .icon bundle are staged into one directory, which
actool compiles into the asset catalog Assets.car that names the icon.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=Path, required=True, help="JSON of path to file.")
    parser.add_argument("--name", required=True, help="The icon's name, its basename.")
    parser.add_argument("--output", type=Path, required=True, help="Compiled resources.")
    args = parser.parse_args()
    files = json.loads(args.files.read_text(encoding="utf-8"))
    # actool resolves relative paths against $PWD, which is not the sandbox.
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        icon = Path(temporary) / (args.name + ".icon")
        for relative, source in files.items():
            destination = icon / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        result = subprocess.run(
            [
                "xcrun",
                "actool",
                str(icon),
                "--compile",
                str(output),
                "--output-format",
                "human-readable-text",
                "--lightweight-asset-runtime-mode",
                "enabled",
                "--app-icon",
                args.name,
                "--include-all-app-icons",
                "--enable-on-demand-resources",
                "NO",
                "--development-region",
                "en",
                "--target-device",
                "mac",
                "--minimum-deployment-target",
                "26",
                "--platform",
                "macosx",
                "--output-partial-info-plist",
                str(Path(temporary) / "partial.plist"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            sys.exit(result.stdout + result.stderr)


if __name__ == "__main__":
    main()
