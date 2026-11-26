"""
What each of CI's host jobs builds and tests: the lanes of one kind of machine, in a few
Bazel commands.

`aspect ci <host>` runs it after the checks that are no Bazel targets (.aspect/develop.axl).
Linux covers the quality, desktop and android lanes, macOS the desktop and ios lanes. The
ruleset and the root module each run their commands in order on their own server, both at
once; one `bazel test` in the root module covers the scenarios, the add-on modules' desktop
lanes and the mobile release builds and smoke tests, so Bazel schedules them together. The
add-on generator's self-tests follow, each in a server of its own (`addon-template`).

Sections: Targets, Commands, Execution.
"""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tools.addons.lanes import desktop_patterns, releases
from tools.addons.modules import ROOT, all_modules, release_targets
from tools.apps.apps import applications
from tools.ci.work import (
    ANDROID_SETUP,
    LINT_CHECK,
    RULESET_DIR,
    SCENARIOS,
    In,
    Work,
    all_work,
    argv,
    environment,
    lint,
    require_android_environment,
)
from tools.ci.work import run as run_work

# The lanes of each host's job, in the order of LANES.
HOST_LANES = {
    "linux": ("quality", "desktop", "android"),
    "macos": ("desktop", "ios"),
}

# The mobile lane each host builds releases for.
MOBILE = {"linux": "android", "macos": "ios"}

# ==== Targets =================================================================


def example_tests(root: Path) -> list[str]:
    """The patterns of the desktop applications' own tests."""
    return [f"{app.package}/..." for app in applications(root) if "desktop" in app.lanes]


def mobile_targets(lane: str, root: Path) -> list[str]:
    """
    A mobile lane's release builds, with their debug symbols, of the applications and the
    add-on modules' examples that name it, and its smoke suite.
    """
    apps = [
        target
        for app in applications(root)
        if lane in app.lanes
        for target in release_targets(lane, app.package)
    ]
    addons = [
        target
        for module in all_modules(root)
        if lane in module.lanes
        for target in releases(lane, module)
    ]
    return [*apps, *addons, f"{SCENARIOS}:{lane}"]


def addon_patterns(host: str, root: Path) -> list[str]:
    """The desktop lanes of the add-on modules that cover this host's desktop system."""
    return [
        pattern
        for module in all_modules(root)
        if "desktop" in module.lanes and host in module.desktops
        for pattern in desktop_patterns(module)
    ]


# ==== Commands ================================================================


def ruleset_steps() -> list[In]:
    """The ruleset's desktop set, its Android packaging tests included, then its lint."""
    return [
        In(RULESET_DIR, "bazel test --build_tests_only //..."),
        In(RULESET_DIR, f"{LINT_CHECK} //..."),
    ]


def root_steps(host: str, root: Path) -> list[In]:
    """
    The root module's commands: on Linux the lint check first; then the tests of the
    tooling and the applications without their apps; then one `bazel test` of the
    scenarios, the add-on modules and the host's mobile lane.
    """
    lint_check = [lint(root)] if "quality" in HOST_LANES[host] else []
    tools = ["//tools/..."] if "quality" in HOST_LANES[host] else []
    own_tests = " ".join([*tools, *example_tests(root)])
    together = " ".join(
        [
            f"{SCENARIOS}/...",
            *mobile_targets(MOBILE[host], root),
            *addon_patterns(host, root),
        ]
    )
    return [
        *lint_check,
        In(".", f"bazel test --build_tests_only {own_tests}"),
        In(".", f"bazel test -- {together}"),
    ]


def selftests(host: str, root: Path = ROOT) -> list[str]:
    """The add-on generator's self-test in each lane of the host that has one."""
    known = all_work(root)
    return [
        name
        for lane in HOST_LANES[host]
        if (name := f"{lane}:addon-template") in known
        and (not known[name].hosts or host in known[name].hosts)
    ]


# ==== Execution ===============================================================


# The job's Bazel work needs the pinned Android SDK on both hosts: the ruleset's desktop set
# includes its Android packaging tests.
JOB = Work("ci", None, ".", (), android=True)

# `bazel test` with no test among the targets exits with 4 after a successful build.
NO_TESTS = 4


def run_steps(steps: list[In], root: Path) -> int:
    """Run one server's commands in order; the first failing one's code, else 0."""
    for step in steps:
        print(f"[ci] {step.directory}$ {step.command}", flush=True)
        code = subprocess.run(
            argv(JOB, step.command, step.directory),
            cwd=root / step.directory,
            env=environment(),
            check=False,
        ).returncode
        if code not in (0, NO_TESTS):
            return code
    return 0


def run(host: str, root: Path = ROOT) -> int:
    """
    Run a host's job: the Android SDK's setup, both servers' commands at once, then the
    self-tests. Returns the first failing code.
    """
    require_android_environment([JOB], environment())
    run_work([ANDROID_SETUP], root)
    servers = [ruleset_steps(), root_steps(host, root)]
    with ThreadPoolExecutor(len(servers)) as pool:
        codes = list(pool.map(lambda steps: run_steps(steps, root), servers))
    if failed := [code for code in codes if code]:
        return failed[0]
    run_work(selftests(host, root), root)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", choices=sorted(HOST_LANES))
    sys.exit(run(parser.parse_args().host))


if __name__ == "__main__":
    main()
