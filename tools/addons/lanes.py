"""
Run one lane of the add-on modules, with the same commands for every module in addons/.

Each lane runs in the root module over the modules' examples, examples/addons/<module>/,
which consume the modules like applications:

- desktop: the modules' tests, their end-to-end tests in e2e/addons/<module>/ and every
  target of their examples but the projects' apps, for the editor and this machine's
  desktop system, on the desktop systems each addon.pkl names;
- android and ios: each example project's release build with its debug symbols,
  `<lane>_release` (examples/releases.bzl), which carries its own configuration. Tests of
  an example's mobile application, such as an `ios_app_test`, run in the desktop lane of
  the hosts they are compatible with.

`python3 -m tools.addons.lanes <lane> [<module>...]` runs the lane of the named modules, or
of every module whose addon.pkl names it, with one Bazel command for all of them, so their
targets build and test in parallel.
"""

import argparse
import subprocess
import sys
from collections.abc import Sequence

from tools.addons.modules import (
    ROOT,
    AddonModule,
    all_modules,
    choices,
    host,
    module_path,
    release_targets,
)

# `bazel test` with no test among the targets exits with 4 after a successful build.
NO_TESTS = 4


def projects(module: AddonModule) -> tuple[str, ...]:
    """The module's example projects; a lane needs at least one."""
    if not module.projects:
        raise ValueError(f"{module.path}: no example project in {module.examples}/")
    return module.projects


def apps(module: AddonModule) -> list[str]:
    """The apps of the module's example projects."""
    return [f"{module.project_package(project)}:app" for project in projects(module)]


def desktop_patterns(module: AddonModule) -> list[str]:
    """The target patterns of one module's desktop lane."""
    excluded = [f"-{app}" for app in apps(module)] if module.builds_apps else []
    tests = [f"//{module.tests.as_posix()}/..."] if module.end_to_end else []
    return [f"@{module.name}//...", f"{module.package}/...", *tests, *excluded]


def releases(lane: str, module: AddonModule) -> list[str]:
    """The release builds of a mobile lane of the module's example projects."""
    return [
        target
        for project in projects(module)
        for target in release_targets(lane, module.project_package(project))
    ]


def command(lane: str, modules: Sequence[AddonModule]) -> list[str]:
    """The Bazel command of one lane, run in the root module."""
    if lane == "desktop":
        patterns = [p for module in modules for p in desktop_patterns(module)]
        return ["bazel", "test", "--", *patterns]
    return ["bazel", "build", *[t for module in modules for t in releases(lane, module)]]


def runnable(lane: str, modules: Sequence[AddonModule]) -> list[AddonModule]:
    """
    The modules whose lane runs here: a module must name the lane, and its desktop lane
    runs on the desktop systems it names only.
    """
    if missing := [module for module in modules if lane not in module.lanes]:
        sys.exit(f"{missing[0].path}: its addon.pkl names no {lane} lane")
    chosen = []
    for module in modules:
        if lane == "desktop" and host() not in module.desktops:
            print(
                f"{module.path}: its desktop lane covers {', '.join(module.desktops)},"
                f" not {host()}"
            )
            continue
        chosen.append(module)
    return chosen


def run(lane: str, modules: Sequence[AddonModule]) -> None:
    modules = runnable(lane, modules)
    if not modules:
        return
    argv = command(lane, modules)
    print("+", " ".join(argv), flush=True)
    status = subprocess.run(argv, cwd=ROOT, check=False).returncode
    if status not in (0, NO_TESTS):
        sys.exit(status)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=choices()["lanes"])
    parser.add_argument(
        "modules", nargs="*", help="modules' directories below addons/; none for all"
    )
    args = parser.parse_args()
    modules = (
        [AddonModule.load(module_path(name)) for name in args.modules]
        if args.modules
        else [module for module in all_modules() if args.lane in module.lanes]
    )
    run(args.lane, modules)


if __name__ == "__main__":
    main()
