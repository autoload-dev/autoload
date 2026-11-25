"""
The add-on generator's self-test in one lane: a fresh module from the template, then its lane.

`python3 -m tools.addons.selftest <lane>` writes addons/selftest and examples/addons/selftest,
declares the module in the root's generated declarations (tools/addons/declarations.py) and
runs the lane. Afterwards it removes both, declares the add-on modules of the checkout alone
again and restores the root's MODULE.bazel.lock, which the run's Bazel commands update, also
when the lane fails, so the checkout is as before.
"""

import argparse
import shutil
from pathlib import Path

from tools.addons import declarations, lanes
from tools.addons.modules import LANES, ROOT, AddonModule, examples_path, module_path
from tools.addons.new import generate
from tools.setup.modules import SELFTEST

LOCK = "MODULE.bazel.lock"


def remove(root: Path) -> None:
    """Remove the self-test's module and examples."""
    shutil.rmtree(root / module_path(SELFTEST), ignore_errors=True)
    shutil.rmtree(root / examples_path(SELFTEST), ignore_errors=True)


def run(lane: str, root: Path = ROOT) -> None:
    lock = root / LOCK
    saved = lock.read_bytes() if lock.is_file() else None
    # A run that ended before its cleanup may have left the module behind.
    remove(root)
    try:
        generate(SELFTEST, root=root, release=False)
        declarations.write(root, extra=(SELFTEST,))
        lanes.run(lane, [AddonModule.load(module_path(SELFTEST), root)])
    finally:
        remove(root)
        declarations.write(root)
        if saved is not None:
            lock.write_bytes(saved)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=LANES)
    run(parser.parse_args().lane)


if __name__ == "__main__":
    main()
