"""
Regenerate the repository's generated files, or check that they are current.

| Generated files | Regenerated here | Checked here |
|---|---|---|
| The MODULE.bazel.lock of the root module and the ruleset's modules | `bazel mod deps --lockfile_mode=update` | `--lockfile_mode=error` |
| The lock files of source-built engines, such as Petri's | no: `bazel run @<hub>//:pin` needs an execution platform for each recipe | analysing the hub's toolchains, which fails on a stale pin |

`aspect generate [PATH...]` regenerates what depends on the paths, as the pre-commit hook
(`aspect pre-commit`) passes the staged ones, or everything without paths. `--check` checks
every generated file, as the pre-push hook and CI's quality lane do. Bazel runs in each file's own module.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from tools.setup.modules import RULESET, module_paths

ROOT = Path(__file__).resolve().parents[2]
RULESET_DIR = RULESET.as_posix()
# The add-on modules' lock files are left out until all of them regenerate: rules_jvm_external's
# maven extension fails to evaluate in autoload_gdunit and its examples, whose root modules
# declare no `maven` of their own to choose between the lock files rules_godot and protobuf
# give it (rules_jvm_external 7.2).
LOCKED_MODULES = tuple(
    module for module in map(str, module_paths(ROOT)) if not module.startswith("addons")
)
# The source builds with a lock file, as (module, hub).
PINNED_ENGINES = ((f"{RULESET_DIR}/examples", "godot_petri"),)


def bazel(module: str, *args: str) -> int:
    return subprocess.run(["bazel", *args], cwd=ROOT / module, check=False).returncode


def is_ruleset_code(path: str) -> bool:
    """A .bzl file of the ruleset that is not one of its tests."""
    in_ruleset = path.startswith(f"{RULESET_DIR}/godot/")
    return in_ruleset and path.endswith(".bzl") and "/tests/" not in path


def locked_modules_shaped_by(paths: list[str]) -> list[str]:
    """
    The locked modules whose lock files the changed files can change: a module through
    its MODULE.bazel, the ruleset's modules through the ruleset's code.
    """
    shaped = {
        str(Path(path).parent) for path in paths if Path(path).name == "MODULE.bazel"
    }
    if any(map(is_ruleset_code, paths)):
        shaped.update(m for m in LOCKED_MODULES if m.startswith(RULESET_DIR))
    return [module for module in LOCKED_MODULES if module in shaped]


def lock_files(modules: list[str], mode: str) -> int:
    status = 0
    for module in modules:
        status |= bazel(module, "mod", "deps", f"--lockfile_mode={mode}")
    return status


def check_lock_files() -> int:
    status = lock_files(list(LOCKED_MODULES), "error")
    if status:
        print("A MODULE.bazel.lock is stale: run `aspect generate`.", file=sys.stderr)
    return status


def pins() -> int:
    status = 0
    for module, hub in PINNED_ENGINES:
        failed = bazel(
            module, "build", "--nobuild", "--keep_going", f"@{hub}//toolchains:all"
        )
        if failed:
            print(
                f"{module}: a pin of @{hub} is stale or the hub does not analyse; pin it "
                f"there with `bazel run @{hub}//:pin --config=buildbuddy`.",
                file=sys.stderr,
            )
        status |= failed
    return status


def regenerate(paths: list[str]) -> int:
    """Regenerate what depends on the paths, or everything without paths."""
    everything = not paths
    modules = list(LOCKED_MODULES) if everything else locked_modules_shaped_by(paths)
    return lock_files(modules, "update")


def check() -> int:
    """Check every generated file."""
    return check_lock_files() | pins()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument(
        "paths", nargs="*", help="changed files; none regenerates everything"
    )
    parser.add_argument("--check", action="store_true", help="check every generated file")
    args = parser.parse_args()
    return check() if args.check else regenerate(args.paths)


if __name__ == "__main__":
    sys.exit(main())
