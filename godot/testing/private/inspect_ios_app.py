"""
Inspect an iOS application: linked symbols, bundled files, Info.plist and dSYM.

The check reads the .app directory or unpacks the .ipa rules_apple builds and
looks at what reaches the application: symbols defined in its executable, files in its bundle and keys of
its Info.plist, and whether its dSYM matches the executable. No simulator or
device runs the application.
"""

import argparse
import plistlib
import subprocess
import tempfile
from pathlib import Path

from godot.testing.private.apple_bundle import application_bundle
from godot.testing.private.native_symbols import macho_uuids


def inspect(args: argparse.Namespace, work: Path) -> None:
    """Raise on anything the application lacks."""
    app = application_bundle(args.app, work)
    info = plistlib.loads((app / "Info.plist").read_bytes())
    executable = app / info["CFBundleExecutable"]
    # Defined symbols, local ones included: an exported symbols list, such as
    # static extension libraries add, keeps everything else out of the exports.
    symbols = {
        line.split()[-1]
        for line in subprocess.run(
            ["/usr/bin/nm", "-U", str(executable)],
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout.splitlines()
        if line.strip()
    }
    problems = [f"symbol {s}" for s in args.symbol if "_" + s not in symbols]
    problems += [f"file {f}" for f in args.file if not (app / f).exists()]
    problems += [f"Info.plist key {k}" for k in args.infoplist_key if k not in info]
    if args.dsym_required:
        # rules_apple names the dSYM's DWARF file after the executable.
        dwarf = [path for path in args.dsym if path.parent.name == "DWARF"]
        uuids = macho_uuids(executable.read_bytes())
        if not dwarf:
            problems.append("a dSYM; build it with --apple_generate_dsym")
        elif any(macho_uuids(path.read_bytes()) != uuids for path in dwarf):
            problems.append("a dSYM with the executable's UUID")
    if problems:
        raise ValueError("The application lacks: " + ", ".join(problems))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--infoplist-key", action="append", default=[])
    parser.add_argument(
        "--dsym-required", action="store_true", help="The application has a dSYM."
    )
    parser.add_argument(
        "--dsym", action="append", default=[], type=Path, help="A file of its dSYM."
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ios-app-") as temporary:
        inspect(args, Path(temporary))
    print("rules_godot: iOS application verified")


if __name__ == "__main__":
    main()
