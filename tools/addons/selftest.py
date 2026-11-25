"""
The add-on generator's self-test in one lane: a fresh module from the template, then its lane.

`python3 -m tools.addons.selftest <lane>` writes addons/.selftest and examples/addons/selftest,
declares the module in the root's MODULE.bazel and runs the lane. Afterwards it removes both
and restores the root's MODULE.bazel and MODULE.bazel.lock, also when the lane fails, so the
checkout is as before.
"""

import argparse
import shutil
from pathlib import Path

from tools.addons import lanes
from tools.addons.modules import LANES, ROOT, AddonModule, examples_path, module_path
from tools.addons.new import declaration, generate

# The self-test's module, which the leading dot keeps out of the add-on modules; it is never
# released.
SELFTEST = ".selftest"

# The root's files that declaring the module changes.
DECLARATIONS = ("MODULE.bazel", "MODULE.bazel.lock")


def remove(root: Path) -> None:
    """Remove the self-test's module and examples."""
    shutil.rmtree(root / module_path(SELFTEST), ignore_errors=True)
    shutil.rmtree(root / examples_path(SELFTEST), ignore_errors=True)


def run(lane: str, root: Path = ROOT) -> None:
    # A run that ended before its cleanup may have left the module declared.
    manifest = root / "MODULE.bazel"
    manifest.write_text(manifest.read_text().replace(declaration(SELFTEST), ""))
    saved = {
        name: (root / name).read_bytes()
        for name in DECLARATIONS
        if (root / name).exists()
    }
    remove(root)
    try:
        generate(SELFTEST, root=root, release=False)
        lanes.run(lane, AddonModule.load(module_path(SELFTEST), root))
    finally:
        remove(root)
        for name, content in saved.items():
            (root / name).write_bytes(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=LANES)
    run(parser.parse_args().lane)


if __name__ == "__main__":
    main()
