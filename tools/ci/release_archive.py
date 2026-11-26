"""
Test a module's release archive the way the Bazel Central Registry does.

`python3 -m tools.ci.release_archive [<module directory>...]` builds each module's archive
from HEAD with the `git archive` arguments of .github/workflows/release_prep.sh, extracts it
and runs the registry test module its presubmit.yml names (RG020) with `bazel test //...`
inside the extracted archive. Without directories, it tests the ruleset and every add-on
module. It is also how to run a registry test module in this repository.

`--in-place`, as CI's macOS job passes it, runs each registry test module where it is in the
checkout instead, with the rules beside it, and leaves its Bazel server up for the next run:
the archive leaves out only files of development, such as the modules' own tests, which no
registry test module reads.

An add-on module's archive resolves autoload_rules_godot from the registry. In this
repository it uses the ruleset of this checkout instead, since an add-on may need rules that
are not released yet; `--registry`, as the release workflow passes it, keeps the version
the module declares, which its consumers get. Each module of a checkout extracts to the
same directory every time, with its Bazel output base beside it.
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.addons.modules import ROOT
from tools.addons.registry import presubmit, registry_test_module
from tools.setup.modules import RULESET, is_released, module_paths

# Where the archives are extracted, one directory per module.
ARCHIVES = Path(tempfile.gettempdir()) / "autoload-release-archives"
# The directory the release archive holds the module's files in, as release_prep.sh names it.
PREFIX = "release"


def test_module(directory: str, root: Path = ROOT) -> str:
    """The registry test module of a module, relative to its archive, from presubmit.yml."""
    path = root / presubmit(Path(directory))
    found = registry_test_module(path.read_text() if path.is_file() else "")
    if found is None:
        raise ValueError(f"{presubmit(Path(directory))}: no bcr_test_module")
    return found


def archive(directory: str, ref: str = "HEAD") -> list[str]:
    """The `git archive` command of a module's release archive (release_prep.sh)."""
    return [
        "git",
        "archive",
        "--format=tar",
        f"--prefix={PREFIX}/",
        "--add-file=LICENSE",
        f"{ref}:{directory}",
    ]


def extract(directory: str, destination: Path, root: Path = ROOT) -> Path:
    """Replace the destination with the module's archive of HEAD; return its module root."""
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True)
    tar = subprocess.run(archive(directory), cwd=root, check=True, capture_output=True)
    subprocess.run(["tar", "-x", "-C", str(destination)], input=tar.stdout, check=True)
    return destination / PREFIX


def command(
    directory: str, output_base: Path, root: Path = ROOT, registry: bool = False
) -> list[str]:
    """
    The registry's test command; an add-on module uses this checkout's ruleset unless the
    registry's is asked for.
    """
    local = not registry and directory != RULESET.as_posix()
    overrides = (
        [f"--override_module=autoload_rules_godot={root / RULESET}"] if local else []
    )
    return ["bazel", f"--output_base={output_base}", "test", *overrides, "//..."]


def workspace(directory: str, root: Path = ROOT) -> Path:
    """Where a checkout extracts a module's archive and keeps its output base."""
    checkout = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    return ARCHIVES / checkout / directory.replace("/", "_")


def test(directory: str, root: Path = ROOT, registry: bool = False) -> int:
    """Test one module's archive; the result is Bazel's exit status."""
    extracted = workspace(directory, root)
    cwd = extract(directory, extracted / "archive", root) / test_module(directory, root)
    argv = command(directory, extracted / "output_base", root, registry)
    print(f"+ {cwd}$ {' '.join(argv)}", flush=True)
    status = subprocess.run(argv, cwd=cwd, check=False).returncode
    subprocess.run([*argv[:2], "shutdown"], cwd=cwd, check=False, capture_output=True)
    return status


def in_place(directory: str, root: Path = ROOT) -> tuple[Path, list[str]]:
    """
    Where and how a module's registry test module runs in the checkout: its settings name
    the rules beside it (addons/bcr.bazelrc).
    """
    return root / directory / test_module(directory, root), ["bazel", "test", "//..."]


def test_in_place(directory: str, root: Path = ROOT) -> int:
    """Test one module's registry test module in the checkout; the result is Bazel's exit status."""
    cwd, argv = in_place(directory, root)
    print(f"+ {cwd}$ {' '.join(argv)}", flush=True)
    return subprocess.run(argv, cwd=cwd, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directories", nargs="*", help="such as rules_godot or addons/<module>"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--registry",
        action="store_true",
        help="resolve autoload_rules_godot as the module declares it, as a release does",
    )
    mode.add_argument(
        "--in-place",
        action="store_true",
        help="run each registry test module in the checkout, without building the archive",
    )
    args = parser.parse_args()
    directories = args.directories or [
        module for module in module_paths(ROOT) if is_released(module)
    ]
    failed = [
        d
        for d in directories
        if (test_in_place(d) if args.in_place else test(d, registry=args.registry)) != 0
    ]
    if failed:
        print(f"Modules that fail their registry test module: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
