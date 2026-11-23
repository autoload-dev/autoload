"""
Pin source engine recipes: configure one recipe into its pin, or merge pins into a lock file.

`recipe` runs in a build action on an execution platform whose host Godot accepts for the
recipe, such as a remote Linux executor for a Linux recipe. It extracts and patches the
source archive as the recipe repository does, adds the repository's custom modules, and
configures the result. `merge` writes the lock file a source build's `lock_file` names.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

try:
    from . import configure
except ImportError:
    # Run as a binary, the tool imports its sibling modules from its own directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import configure  # type: ignore[no-redef]


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


def apply_patches(source: Path, patches: list[str], strip: int) -> None:
    """Apply each patch strictly, with fuzz disabled, as the recipe repository does."""
    for patch in patches:
        subprocess.run(
            ["patch", f"-p{strip}", "-F0", "-t", "-N", "-i", str(Path(patch).resolve())],
            cwd=source,
            check=True,
        )


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


def merge(arguments: argparse.Namespace) -> None:
    """
    Write the lock file of a source build's recipe pins.

    Recipes of one build target share their generators whatever the platform or CPU, so
    the lock stores each distinct generator list once, by its digest.
    """
    recipes = {}
    generators = {}
    for declaration in arguments.recipe:
        key, _, path = declaration.partition("=")
        pin = json.loads(Path(path).read_text())
        shared = pin["graph"]["generators"]
        reference = "sha256:" + configure.digest_of(shared)
        generators[reference] = shared
        pin["graph"]["generators"] = reference
        recipes[key] = pin
    lock = {
        "generators": dict(sorted(generators.items())),
        "recipes": dict(sorted(recipes.items())),
    }
    # Only the tables are sorted; one space per level keeps the lock small.
    configure.write_json(Path(arguments.output), lock, indent=1)


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
    arguments, rest = parser.parse_known_args()
    if arguments.command == "recipe":
        recipe(arguments, rest)
    else:
        merge(arguments)


if __name__ == "__main__":
    main()
