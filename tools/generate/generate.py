"""
Regenerate the repository's generated files, or check that they are current.

| Generated files | Regenerated here | Checked here |
|---|---|---|
| The root module's declarations of the add-on modules, addons.MODULE.bazel | from the modules of addons/ (tools/addons/declarations.py) | the same, failing when it differs |
| The MODULE.bazel.lock of the root module and the ruleset's modules | `bazel mod deps --lockfile_mode=update` | the same, failing when it changes a lock file |
| The lock files of source-built engines, such as an application's | no: `bazel run @<hub>//:pin` needs an execution platform for each recipe | analysing the hub's toolchains, which fails on a stale pin |

`aspect generate [PATH...]` regenerates what depends on the paths, as the pre-commit hook
(`aspect pre-commit`) passes the staged ones, or everything without paths. `--check` checks
every generated file, as the pre-push hook and CI's quality lane do. Bazel runs in each file's own module.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from tools.addons import declarations
from tools.setup.modules import ADDONS, RULESET, module_paths

ROOT = Path(__file__).resolve().parents[2]
RULESET_DIR = RULESET.as_posix()
# The add-on modules' lock files are left out until all of them regenerate: rules_jvm_external's
# maven extension fails to evaluate in autoload_gdunit and its examples, whose root modules
# declare no `maven` of their own to choose between the lock files rules_godot and protobuf
# give it (rules_jvm_external 7.2).
LOCKED_MODULES = tuple(
    module for module in map(str, module_paths(ROOT)) if not module.startswith("addons")
)
# A source build's lock file, which RG014 keeps in engine/ of its project:
# engine/<hub>.lock.json.
LOCK_SUFFIX = ".lock.json"


def pinned_engines(root: Path = ROOT) -> tuple[tuple[str, str], ...]:
    """The source builds with a lock file, as (module, hub): the applications' of examples/."""
    return tuple(
        (".", path.name.removesuffix(LOCK_SUFFIX))
        for path in sorted(root.glob(f"examples/*/engine/*{LOCK_SUFFIX}"))
    )


def bazel(module: str, *args: str) -> int:
    return subprocess.run(["bazel", *args], cwd=ROOT / module, check=False).returncode


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


def lock_files(modules: list[str]) -> int:
    status = 0
    for module in modules:
        status |= bazel(module, "mod", "deps", "--lockfile_mode=update")
    return status


def lock_file(module: str) -> bytes | None:
    """A module's lock file, or none before Bazel writes it."""
    path = ROOT / module / "MODULE.bazel.lock"
    return path.read_bytes() if path.is_file() else None


def check_lock_files() -> int:
    """
    Regenerate every lock file and fail when one changes or appears. Bazel's default mode,
    `update`, as every other command uses it, not `--lockfile_mode=error`: a server whose
    lock file mode changes reloads every package on its next command, which later checks
    would pay for.
    """
    before = {module: lock_file(module) for module in LOCKED_MODULES}
    status = lock_files(list(LOCKED_MODULES))
    stale = [
        f"{module}/MODULE.bazel.lock"
        for module, text in before.items()
        if lock_file(module) != text
    ]
    if stale:
        print(
            f"Stale lock files, now regenerated; commit them: {', '.join(stale)}",
            file=sys.stderr,
        )
        return 1
    return status


def pins() -> int:
    status = 0
    for module, hub in pinned_engines():
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


def segment(check: bool = False) -> int:
    """Write the root module's declarations of the add-on modules, or check them."""
    if not check:
        declarations.write(ROOT)
        return 0
    if declarations.is_current(ROOT):
        return 0
    print(
        f"Stale {declarations.SEGMENT}; regenerate it with `aspect generate`.",
        file=sys.stderr,
    )
    return 1


def regenerate(paths: list[str]) -> int:
    """Regenerate what depends on the paths, or everything without paths."""
    everything = not paths
    modules = list(LOCKED_MODULES) if everything else locked_modules_shaped_by(paths)
    return segment() | lock_files(modules)


def check() -> int:
    """Check every generated file."""
    return segment(check=True) | check_lock_files() | pins()


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
