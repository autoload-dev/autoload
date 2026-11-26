"""
Regenerate the repository's generated files, or check that they are current.

| Generated files | Regenerated here | Checked here |
|---|---|---|
| The root module's declarations of the add-on modules, addons.MODULE.bazel | from the modules of addons/ (tools/addons/declarations.py) | the same, failing when it differs |
| The MODULE.bazel.lock of the root module and the ruleset's modules | `bazel mod deps --lockfile_mode=update` | the same, failing when it changes a lock file |
| The lock files of source-built engines, those the root module's `godot_engines.engine` tags name | no: `bazel run @<hub>//:pin` needs an execution platform for each recipe | analysing each recipe the lock file pins, which fails on a stale pin |

`aspect generate [PATH...]` regenerates what depends on the paths, as the pre-commit hook
(`aspect pre-commit`) passes the staged ones, or everything without paths. `--check` checks
every generated file, as the pre-push hook and CI's quality lane do. Bazel runs in each
file's own module.

Sections: Lock files, Pinned engines, Entry points.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from tools.addons import declarations
from tools.setup.modules import ADDONS, RULESET, label_path, literals, module_paths
from tools.setup.modules import declarations as module_declarations

ROOT = Path(__file__).resolve().parents[2]


def bazel(module: str, *args: str) -> int:
    return subprocess.run(["bazel", *args], cwd=ROOT / module, check=False).returncode


# ==== Lock files ==============================================================

RULESET_DIR = RULESET.as_posix()
# The add-on modules' lock files are left out until all of them regenerate: rules_jvm_external's
# maven extension fails to evaluate in autoload_gdunit and its examples, whose root modules
# declare no `maven` of their own to choose between the lock files rules_godot and protobuf
# give it (rules_jvm_external 7.2).
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


# ==== Pinned engines ==========================================================


def pinned_engines(root: Path = ROOT) -> tuple[tuple[str, Path], ...]:
    """
    The engines the root module's MODULE.bazel declares with a lock file, by name. Its
    segments declare no engines, so they are left out.
    """
    engines = []
    for declaration in module_declarations((root / "MODULE.bazel").read_text()):
        if (
            declaration.kind == "godot_engines.engine"
            and "lock_file" in declaration.keywords
        ):
            # A lock_file that is no literal fails here rather than leave its engine unchecked.
            values = literals(declaration.keywords)
            engines.append((values["name"], label_path(root, values["lock_file"])))
    return tuple(engines)


def repo_mapping() -> dict[str, str]:
    """The root module's repository mapping: each apparent name's canonical name."""
    result = subprocess.run(
        ["bazel", "mod", "dump_repo_mapping", ""],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def pinned_payloads(hub: str, lock: Path, mapping: dict[str, str]) -> list[str]:
    """
    The engine library of each recipe a lock file pins, by canonical label.

    A recipe the lock file leaves unpinned, such as one of a platform no execution platform
    configured, fails only when a build needs it, so the check leaves it out.
    """
    text = lock.read_text().strip()
    recipes = json.loads(text).get("recipes", {}) if text else {}
    return [f"@@{mapping[hub]}_{key}//:engine_library" for key in sorted(recipes)]


def pins() -> int:
    status = 0
    engines = pinned_engines()
    mapping = repo_mapping() if engines else {}
    for hub, lock in engines:
        if hub not in mapping:
            print(
                f"{lock.relative_to(ROOT)} pins the engine {hub}, which the root module's "
                f"MODULE.bazel does not use_repo; add it.",
                file=sys.stderr,
            )
            status = 1
            continue
        payloads = pinned_payloads(hub, lock, mapping)
        if not payloads:
            continue
        # A recipe's targets are compatible with its own platform only.
        failed = bazel(
            ".",
            "build",
            "--nobuild",
            "--keep_going",
            "--skip_incompatible_explicit_targets",
            *payloads,
        )
        if failed:
            print(
                f"a pin of @{hub} is stale or its recipes do not analyse; pin them with "
                f"`bazel run @{hub}//:pin --config=buildbuddy`, or one platform's with "
                f"`:pin_<platform>`.",
                file=sys.stderr,
            )
        status |= failed
    return status


# ==== Entry points ============================================================


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
