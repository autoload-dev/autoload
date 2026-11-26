"""
The add-on generator's self-test in one lane: a fresh module from the template, then its lane.

`python3 -m tools.addons.selftest <lane>` writes addons/selftest and examples/addons/selftest,
declares the module in the root's generated declarations (tools/addons/declarations.py) and
runs the lane; its desktop lane also runs the module's registry test module, bcr/smoke.
Its declaration changes the root's module graph, so it updates the root's MODULE.bazel.lock
before the lane, whose commands fail on a stale one in CI (--config=ci, shared.bazelrc).
Afterwards it removes both, declares the add-on modules of the checkout alone again and
restores MODULE.bazel.lock, also when the lane fails, so the checkout is as before.
"""

import argparse
import shutil
import subprocess
from pathlib import Path

from tools.addons import declarations, lanes
from tools.addons.modules import ROOT, AddonModule, choices, examples_path, module_path
from tools.addons.new import generate
from tools.setup.modules import BCR, SELFTEST

LOCK = "MODULE.bazel.lock"


def remove(root: Path) -> None:
    """Remove the self-test's module and examples."""
    shutil.rmtree(root / module_path(SELFTEST), ignore_errors=True)
    shutil.rmtree(root / examples_path(SELFTEST), ignore_errors=True)


def update_lock_file(root: Path) -> None:
    """Update the root's MODULE.bazel.lock for the module graph with the self-test's module."""
    command = ["bazel", "mod", "deps", "--lockfile_mode=update"]
    print(f"+ {root}$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=root, check=True, stdout=subprocess.DEVNULL)


def test_registry_module(root: Path) -> None:
    """
    Run the module's registry test module in place, with the rules of this checkout
    (addons/bcr.bazelrc), so that the template's bcr/smoke builds before any release.
    """
    cwd = root / module_path(SELFTEST) / BCR / "smoke"
    print(f"+ {cwd}$ bazel test //...", flush=True)
    try:
        subprocess.run(["bazel", "test", "//..."], cwd=cwd, check=True)
    finally:
        subprocess.run(["bazel", "shutdown"], cwd=cwd, check=False, capture_output=True)


def run(lane: str, root: Path = ROOT) -> None:
    lock = root / LOCK
    saved = lock.read_bytes() if lock.is_file() else None
    # A run that ended before its cleanup may have left the module behind.
    remove(root)
    try:
        generate(SELFTEST, root=root, release=False)
        declarations.write(root, extra=(SELFTEST,))
        update_lock_file(root)
        lanes.run(lane, [AddonModule.load(module_path(SELFTEST), root)])
        if lane == "desktop":
            test_registry_module(root)
    finally:
        remove(root)
        declarations.write(root)
        if saved is not None:
            lock.write_bytes(saved)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=choices()["lanes"])
    run(parser.parse_args().lane)


if __name__ == "__main__":
    main()
