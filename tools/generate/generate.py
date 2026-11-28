"""
Regenerate the repository's generated files.

| Generated files | Regenerated here | Checked |
|---|---|---|
| The root module's declarations of the add-on modules, addons.MODULE.bazel | from the modules of addons/ (tools/addons/declarations.py) | by Bazel itself, which fails to load a stale one (see there) |
| The add-on modules' shared files, such as their .bazelrc, LICENSE and registry templates | from the add-on generator's template (tools/addons/new.py) | by the file lint's convention rule shared-module-files-as-generated |
| The ruleset's LICENSE, a copy of the repository's | from the repository's LICENSE | by //tools/ci:released_modules_carry_the_license_test, with the add-on modules' |
| The MODULE.bazel.lock of the root module and the ruleset's modules | `bazel mod deps --lockfile_mode=update` | by every CI command, whose `--config=ci` sets `--lockfile_mode=error` (shared.bazelrc) |
| The lock files of source-built engines, those the root module's `godot_engines.engine` tags name | no: `bazel run @<hub>//:pin` needs an execution platform for each recipe | by a `build_test` of the hub's `:pinned` beside each, which fails on a stale pin |

`aspect generate [PATH...]` regenerates what depends on the paths, as the pre-commit hook
(`aspect pre-commit`) passes the staged ones, or everything without paths. Bazel runs in each
file's own module.

Sections: Lock files, Shared files, Entry points.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from tools.addons import declarations, new
from tools.setup.modules import ADDONS, RULESET, module_paths

ROOT = Path(__file__).resolve().parents[2]


# ==== Lock files ==============================================================

RULESET_DIR = RULESET.as_posix()
# The add-on modules keep no lock file (their .gitignore): the root module, which builds their
# examples, pins their dependencies.
LOCKED_MODULES = tuple(
    module for module in map(str, module_paths(ROOT)) if not module.startswith("addons")
)


def is_ruleset_code(path: str) -> bool:
    """A .bzl file of the ruleset that is not one of its tests."""
    in_ruleset = path.startswith(f"{RULESET_DIR}/godot/")
    return in_ruleset and path.endswith(".bzl") and "/tests/" not in path


def is_addon_manifest(path: str) -> bool:
    """An add-on module's MODULE.bazel, which the root module's declarations include."""
    return Path(path).parent.parent == Path(ADDONS) and Path(path).name == "MODULE.bazel"


def locked_modules_shaped_by(paths: list[str]) -> list[str]:
    """
    The locked modules whose lock files the changed files can change: a module through
    its MODULE.bazel or segments, the root module through the add-on modules it declares,
    and the ruleset and the root module, which consumes it, through the ruleset's code.
    """
    shaped = {str(Path(path).parent) for path in paths if path.endswith("MODULE.bazel")}
    if any(map(is_addon_manifest, paths)):
        shaped.add(".")
    if any(map(is_ruleset_code, paths)):
        shaped.update((".", RULESET_DIR))
    return [module for module in LOCKED_MODULES if module in shaped]


def bazel(module: str, *args: str) -> int:
    return subprocess.run(["bazel", *args], cwd=ROOT / module, check=False).returncode


def lock_files(modules: list[str]) -> int:
    status = 0
    for module in modules:
        status |= bazel(module, "mod", "deps", "--lockfile_mode=update")
    return status


# ==== Shared files ============================================================


def unstaged_files() -> list[str]:
    """The files whose working-tree contents differ from what Git's index stages."""
    output = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return output.splitlines()


def stale_ruleset_license(root: Path) -> dict[Path, str]:
    """
    The ruleset's copy of the repository's license if it differs, by path relative to root:
    its release archive and package metadata carry it, as the add-on modules' do theirs.
    """
    return new.stale(root, {RULESET / new.LICENSE: (root / new.LICENSE).read_text()})


def shared_files(paths: list[str]) -> int:
    """
    Write the add-on modules' shared files that differ from what the generator writes, and
    the ruleset's license. With paths, as the pre-commit hook passes the staged files, a
    shared file that holds edits, staged among the paths or unstaged, is not overwritten:
    the run fails instead.
    """
    stale = new.stale_shared_files(ROOT) | stale_ruleset_license(ROOT)
    edited = set(paths) | set(unstaged_files()) if paths else set()
    if overwritten := sorted(p.as_posix() for p in stale if p.as_posix() in edited):
        print(
            "The add-on generator writes the add-on modules' shared files; change its "
            "template (tools/addons/template) instead of: " + ", ".join(overwritten)
        )
        return 1
    new.write_files(ROOT, stale)
    return 0


# ==== Entry points ============================================================


def regenerate(paths: list[str]) -> int:
    """
    Write the root module's declarations of the add-on modules and their shared files, and
    regenerate the MODULE.bazel.lock files that depend on the paths, or all of them without
    paths.
    """
    declarations.write(ROOT)
    if shared_files(paths) != 0:
        return 1
    everything = not paths
    modules = list(LOCKED_MODULES) if everything else locked_modules_shaped_by(paths)
    return lock_files(modules)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument(
        "paths", nargs="*", help="changed files; none regenerates everything"
    )
    args = parser.parse_args()
    return regenerate(args.paths)


if __name__ == "__main__":
    sys.exit(main())
