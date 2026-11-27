"""
Pin source engine recipes: configure one recipe into its pin, or merge pins into a lock file.

`recipe` runs in a build action on an execution platform whose host Godot accepts for the
recipe, such as a remote Linux executor for a Linux recipe. It extracts the source archive
and applies the recipe's patches as the recipe repository does, adds the structure of the
repository's custom modules with placeholders of their code, and configures the result.
`merge` and `update` write the lock file an engine's `lock_file` names, as lock.py does.
"""

import argparse
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

try:
    from . import configure, custom_modules
    from .lock import merge, update
    from .patches import apply_patches
except ImportError:
    # Run as a binary, the tool imports its sibling modules from its own directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import configure
    import custom_modules
    from lock import merge, update
    from patches import apply_patches


def copy_tree(root: Path, files: list[str], destination: Path) -> None:
    """Copy each file below root to the same relative path below destination."""
    for name in files:
        path = Path(name)
        target = destination / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def extract(archive: Path, strip_prefix: str, destination: Path) -> None:
    """Extract the archive's entries below strip_prefix into destination."""
    prefix = strip_prefix.strip("/") + "/" if strip_prefix else ""
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                if entry.is_dir() or not entry.filename.startswith(prefix):
                    continue
                target = destination / entry.filename.removeprefix(prefix)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(entry))
        return
    with tarfile.open(archive) as source:
        members = []
        for member in source.getmembers():
            if member.name.startswith(prefix) and member.name != prefix:
                member.name = member.name.removeprefix(prefix)
                if member.islnk():
                    # A hard link names its target by its path in the archive.
                    member.linkname = member.linkname.removeprefix(prefix)
                members.append(member)
        source.extractall(destination, members=members, filter="data")


def recipe(arguments: argparse.Namespace, configure_arguments: list[str]) -> None:
    root = Path(arguments.root)
    files = Path(arguments.files).read_text().splitlines()
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        source = work / "source"
        extract(Path(arguments.archive), arguments.strip_prefix, source)
        apply_patches(source, arguments.patch, arguments.patch_strip)
        scons = [name for name in files if name.startswith(f"{root}/_scons/")]
        copy_tree(root, [name for name in files if name not in scons], source)
        # The custom modules' code comes by label; their structure is what configures.
        custom_modules.write_placeholders(source)
        copy_tree(root / "_scons", scons, work / "scons")
        configure.main(
            [
                "--source",
                str(source),
                "--scons",
                str(work / "scons"),
                "--pin-output",
                arguments.output,
                "--patch-strip",
                str(arguments.patch_strip),
                *(f"--patch={patch}" for patch in arguments.patch),
                *configure_arguments,
            ]
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    pin = commands.add_parser("recipe")
    pin.add_argument("--root", required=True, help="The recipe repository's directory.")
    pin.add_argument(
        "--files", required=True, help="A file listing its custom modules and SCons."
    )
    pin.add_argument("--archive", required=True, help="The source archive.")
    pin.add_argument("--strip-prefix", default="")
    pin.add_argument("--patch", action="append", default=[])
    pin.add_argument("--patch-strip", type=int, default=1)
    pin.add_argument("--output", required=True)
    lock = commands.add_parser("merge")
    lock.add_argument("--output", required=True)
    lock.add_argument("--recipe", action="append", default=[], help="key=pin file")
    lock.add_argument(
        "--variant",
        nargs=3,
        action="append",
        default=[],
        metavar=("KEY", "PROFILE", "PIN"),
        help="a recipe's runtime variant: its key, runtime profile label and pin file",
    )
    partial = commands.add_parser("update")
    partial.add_argument(
        "--lock", required=True, type=Path, help="The lock file to update."
    )
    partial.add_argument(
        "--pins", required=True, type=Path, help="A merged partial lock."
    )
    arguments, rest = parser.parse_known_args()
    if arguments.command == "recipe":
        recipe(arguments, rest)
    elif arguments.command == "update":
        update(arguments.lock, arguments.pins)
    else:
        merge(arguments)


if __name__ == "__main__":
    main()
