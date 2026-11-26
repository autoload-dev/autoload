"""
What each of CI's host jobs builds and tests: the lanes of one kind of machine, in a few
Bazel commands.

`aspect ci <host>` runs it after the checks that are no Bazel targets (.aspect/develop.axl).
Linux covers the quality, desktop and android lanes, macOS the desktop and ios lanes. The
ruleset and the root module each run their commands in order on their own server, both at
once; one `bazel test` in the root module covers the scenarios, the add-on modules' desktop
lanes and the mobile release builds and smoke tests, so Bazel schedules them together. The
add-on generator's self-tests follow, each in a server of its own (`addon-template`).

Sections: Hosts, Commands, Execution.
"""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from tools.addons.lanes import NO_TESTS, desktop_patterns, releases
from tools.addons.modules import ROOT, AddonModule, all_modules, release_targets
from tools.apps.apps import Application, applications
from tools.ci import work
from tools.ci.work import LINT_CHECK, RULESET_DIR, SCENARIOS, In, Work

# ==== Hosts ===================================================================


@dataclass(frozen=True)
class Host:
    """The lanes of one host's job: the quality lane or not, the desktop lane, one mobile lane."""

    quality: bool
    mobile: str

    @property
    def lanes(self) -> tuple[str, ...]:
        return (*(("quality",) if self.quality else ()), "desktop", self.mobile)


HOSTS = {
    "linux": Host(quality=True, mobile="android"),
    "macos": Host(quality=False, mobile="ios"),
}


@dataclass(frozen=True)
class Manifests:
    """The applications' and the add-on modules' manifests, each evaluated once."""

    apps: tuple[Application, ...]
    modules: tuple[AddonModule, ...]

    @classmethod
    def load(cls, root: Path) -> Manifests:
        return cls(applications(root), all_modules(root))

    def example_tests(self) -> list[str]:
        """The patterns of the desktop applications' own tests."""
        return [f"{app.package}/..." for app in self.apps if "desktop" in app.lanes]

    def mobile_targets(self, lane: str) -> list[str]:
        """
        A mobile lane's release builds, with their debug symbols, of the applications and
        the add-on modules' examples that name it, and its smoke suite.
        """
        apps = [
            target
            for app in self.apps
            if lane in app.lanes
            for target in release_targets(lane, app.package)
        ]
        addons = [
            target
            for module in self.modules
            if lane in module.lanes
            for target in releases(lane, module)
        ]
        return [*apps, *addons, f"{SCENARIOS}:{lane}"]

    def addon_patterns(self, host: str) -> list[str]:
        """The desktop lanes of the add-on modules that cover this host's desktop system."""
        return [
            pattern
            for module in self.modules
            if "desktop" in module.lanes and host in module.desktops
            for pattern in desktop_patterns(module)
        ]


# ==== Commands ================================================================


def ruleset_steps(host: str) -> list[In]:
    """The ruleset's desktop set, its Android packaging tests included; on Linux its lint."""
    lint = [In(RULESET_DIR, f"{LINT_CHECK} //...")] if HOSTS[host].quality else []
    return [In(RULESET_DIR, "bazel test --build_tests_only //..."), *lint]


def root_steps(host: str, manifests: Manifests, root: Path = ROOT) -> list[In]:
    """
    The root module's commands: on Linux the lint check first; then the tests of the
    tooling and the applications without their apps; then one `bazel test` of the
    scenarios, the add-on modules and the host's mobile lane.
    """
    quality = HOSTS[host].quality
    lint_check, tools = ([work.lint(root)], ["//tools/..."]) if quality else ([], [])
    own_tests = " ".join([*tools, *manifests.example_tests()])
    together = " ".join(
        [
            f"{SCENARIOS}/...",
            *manifests.mobile_targets(HOSTS[host].mobile),
            *manifests.addon_patterns(host),
        ]
    )
    return [
        *lint_check,
        In(".", f"bazel test --build_tests_only {own_tests}"),
        In(".", f"bazel test -- {together}"),
    ]


def selftests(host: str) -> list[str]:
    """
    The add-on generator's self-test in each lane of the host but quality; the work skips
    those limited to other hosts.
    """
    return [f"{lane}:addon-template" for lane in HOSTS[host].lanes if lane != "quality"]


# ==== Execution ===============================================================


# The job's Bazel work needs the pinned Android SDK on both hosts: the ruleset's desktop set
# includes its Android packaging tests.
JOB = Work("ci", None, ".", (), android=True)


def run_steps(steps: list[In], root: Path) -> int:
    """Run one server's commands in order; the first failing one's code, else 0."""
    for step in steps:
        print(f"[ci] {step.directory}$ {step.command}", flush=True)
        code = subprocess.run(
            work.argv(JOB, step.command, step.directory),
            cwd=root / step.directory,
            env=work.environment(),
            check=False,
        ).returncode
        if code not in (0, NO_TESTS):
            return code
    return 0


def run_host(host: str, root: Path = ROOT) -> int:
    """
    Run a host's job: the Android SDK's setup, both servers' commands at once, then the
    self-tests. Returns the first failing code.
    """
    work.require_android_environment([JOB], work.environment())
    work.run([work.ANDROID_SETUP], root)
    manifests = Manifests.load(root)
    servers = [ruleset_steps(host), root_steps(host, manifests, root)]
    with ThreadPoolExecutor(len(servers)) as pool:
        codes = list(pool.map(lambda steps: run_steps(steps, root), servers))
    if failed := next((code for code in codes if code), 0):
        return failed
    work.run(selftests(host), root)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", choices=sorted(HOSTS))
    sys.exit(run_host(parser.parse_args().host))


if __name__ == "__main__":
    main()
