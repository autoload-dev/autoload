"""
Run one lane of the add-on modules, with the same commands for every module in addons/.

Each lane runs in the root module over the modules' examples, examples/addons/<module>/,
which consume the modules like applications:

- desktop: the modules' tests, their end-to-end tests in e2e/addons/<module>/ and every
  target of their examples but the projects' apps, for the editor and this machine's
  desktop system, on the desktop systems each addon.pkl names;
- android and ios: each example project's `app`, for Android and the iOS Simulator, and the
  tests of the example projects tagged with the lane's name, such as an `ios_app_test` of
  the app; `manual` keeps them out of the desktop lane.

`python3 -m tools.addons.lanes <lane> [<module>...]` runs the lane of the named modules, or
of every module whose addon.pkl names it, with one Bazel command for all of them, so their
targets build and test in parallel.
"""

import argparse
import subprocess
import sys
from collections.abc import Sequence

from tools.addons.modules import (
    LANES,
    ROOT,
    AddonModule,
    all_modules,
    host,
    module_path,
)

# The Bazel configuration of each mobile lane, from the root module's .bazelrc.
APP_CONFIGS = {"android": "--config=android", "ios": "--config=official"}
# `bazel test` with no test among the targets exits with 4 after a successful build.
NO_TESTS = 4


def apps(module: AddonModule) -> list[str]:
    """The apps of the module's example projects."""
    if not module.projects:
        raise ValueError(f"{module.path}: no example project in {module.examples}/")
    return [f"{module.project_package(project)}:app" for project in module.projects]


def lane_tests_query(lane: str, modules: Sequence[AddonModule]) -> list[str]:
    """The Bazel query for the example projects' tests that a mobile lane runs."""
    examples = " + ".join(f"{module.package}/..." for module in modules)
    return [
        "bazel",
        "query",
        "--output=label",
        # Query renders tags as "[a, b]": match a whole element, not a tag like no-ios.
        f'attr(tags, "[\\[ ]{lane}[,\\]]", tests({examples}))',
    ]


def desktop_patterns(module: AddonModule) -> list[str]:
    """The target patterns of one module's desktop lane."""
    excluded = [f"-{app}" for app in apps(module)] if module.builds_apps else []
    tests = [f"//{module.tests.as_posix()}/..."] if module.end_to_end else []
    return [f"@{module.name}//...", f"{module.package}/...", *tests, *excluded]


def command(
    lane: str, modules: Sequence[AddonModule], tests: list[str] | None = None
) -> list[str]:
    """The Bazel command of one lane, run in the root module, with a mobile lane's tests."""
    if lane == "desktop":
        patterns = [p for module in modules for p in desktop_patterns(module)]
        return ["bazel", "test", "--", *patterns]
    targets = [app for module in modules for app in apps(module)]
    if not tests:
        return ["bazel", "build", APP_CONFIGS[lane], *targets]
    return ["bazel", "test", APP_CONFIGS[lane], "--", *targets, *tests]


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
    tests = None
    if lane != "desktop":
        query = lane_tests_query(lane, modules)
        print("+", " ".join(query), flush=True)
        found = subprocess.run(
            query, cwd=ROOT, check=True, capture_output=True, text=True
        )
        tests = found.stdout.split()
    argv = command(lane, modules, tests)
    print("+", " ".join(argv), flush=True)
    status = subprocess.run(argv, cwd=ROOT, check=False).returncode
    if status not in ({0, NO_TESTS} if lane == "desktop" else {0}):
        sys.exit(status)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=LANES)
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
