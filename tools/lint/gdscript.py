"""
The GDScript lint: gdlint on every tracked script, or on the given ones, with the rules that
.gdlintrc keeps. `bazel run //tools/lint:gdscript [PATH...]`.
"""

import contextlib
import os
import subprocess
import sys
from pathlib import Path

from gdtoolkit.linter.__main__ import main as gdlint

# Scripts that are not checked, each with its reason.
EXCLUDED = (
    # The validation's fixtures exercise the forms GDScript allows, such as `extends` before
    # `class_name` and a property beside the variable that backs it.
    "rules_godot/godot/private/tests/validation/fixtures/classes/noext.gd",
    "rules_godot/godot/private/tests/validation/fixtures/interface/base/base.gd",
    # A script the validation must reject because it does not parse.
    "rules_godot/godot/private/tests/validation/fixtures/script_errors/parse_error.gd",
)


def scripts(root: Path) -> list[str]:
    """
    The tracked scripts of a checkout but the excluded, relative to its root. Git also lists
    tracked files that were deleted from the working tree, which are left out.
    """
    listed = subprocess.run(
        ["git", "-C", root, "ls-files", "-z", "*.gd"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(
        p for p in listed.split("\0") if p and p not in EXCLUDED and (root / p).is_file()
    )


def main(root: Path, paths: list[str]) -> None:
    """
    Run gdlint in the root, where it reads .gdlintrc, on the given paths, relative to the
    current directory, or on every script; it exits 1 on a problem.
    """
    given = [str(Path(path).resolve()) for path in paths]
    with contextlib.chdir(root):
        sys.argv = ["gdlint", *(given or scripts(root))]
        gdlint()


if __name__ == "__main__":
    os.chdir(os.environ.get("BUILD_WORKING_DIRECTORY", "."))
    main(Path(os.environ["BUILD_WORKSPACE_DIRECTORY"]), sys.argv[1:])
