"""
Test a module's release archive the way the Bazel Central Registry does.

`python3 -m tools.ci.release_archive [<module directory>...]` builds each module's archive
with `git archive` from HEAD, as .github/workflows/release_prep.sh does, extracts it and runs
the registry test module its presubmit.yml names (RG020) with `bazel test //...` inside the
extracted archive. Without directories, it tests the ruleset and every add-on module.

An add-on module's archive resolves autoload_rules_godot from the registry; here it uses the
ruleset of this checkout instead, since an add-on may need rules that are not released yet.
Each module extracts to the same directory every time, so its Bazel output base stays warm.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.addons.modules import ROOT
from tools.addons.registry import presubmit, registry_test_module
from tools.setup.modules import RULESET, addon_modules

# Where the archives are extracted, one directory per module.
ARCHIVES = Path(tempfile.gettempdir()) / "autoload-release-archives"


def test_module(directory: str, root: Path = ROOT) -> str:
    """The registry test module of a module, relative to its archive, from presubmit.yml."""
    path = presubmit(Path(directory))
    found = registry_test_module(
        (root / path).read_text() if (root / path).is_file() else ""
    )
    if found is None:
        raise ValueError(f"{path}: no bcr_test_module")
    return found


def extract(directory: str, destination: Path, root: Path = ROOT) -> None:
    """Replace the destination with the module's archive of HEAD."""
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "archive", "--format=tar", f"HEAD:{directory}"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(destination)], input=archive, check=True)


def command(directory: str, root: Path = ROOT) -> list[str]:
    """The registry's test command, with this checkout's ruleset for an add-on module."""
    overrides = (
        []
        if directory == RULESET.as_posix()
        else [f"--override_module=autoload_rules_godot={root / RULESET}"]
    )
    return ["bazel", "test", *overrides, "//..."]


def test(directory: str, root: Path = ROOT) -> int:
    """Test one module's archive; the result is Bazel's exit status."""
    extracted = ARCHIVES / directory.replace("/", "_")
    extract(directory, extracted, root)
    cwd = extracted / test_module(directory, root)
    print(f"+ {cwd}$ {' '.join(command(directory, root))}", flush=True)
    status = subprocess.run(command(directory, root), cwd=cwd, check=False).returncode
    subprocess.run(["bazel", "shutdown"], cwd=cwd, check=False, capture_output=True)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directories", nargs="*", help="such as rules_godot or addons/sqlite"
    )
    directories = parser.parse_args().directories or [
        RULESET.as_posix(),
        *addon_modules(ROOT),
    ]
    failed = [directory for directory in directories if test(directory) != 0]
    if failed:
        print(f"Release archives that fail their test module: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
