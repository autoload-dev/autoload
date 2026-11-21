"""
Run one lane of an add-on module, with the same commands for every module in addons/.

Each lane runs in the module's examples/, which consumes the module like an application:

- host: the module's tests and every target of its example projects but their apps, for
  the editor and this desktop host;
- android and ios: each example project's `app`, for Android and the iOS Simulator.
"""

import argparse
import platform
import subprocess
import sys
from pathlib import Path

from tools.addons.modules import ROOT, AddonModule

# The Bazel configuration of each mobile lane, from the examples' .bazelrc.
APP_CONFIGS = {"android": "--config=android", "ios": "--config=ios_sim"}
# `bazel test` with no test among the targets exits with 4 after a successful build.
NO_TESTS = 4


def host() -> str:
    """This machine as addon.pkl names hosts."""
    return {"Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system())


def commands(lane: str, module: AddonModule) -> list[list[str]]:
    """The Bazel commands of one lane, run in the module's examples/."""
    if not module.projects:
        raise ValueError(f"{module.path}: no example project in examples/projects/")
    if lane == "host":
        apps = [f"-//projects/{project}:app" for project in module.projects]
        return [["bazel", "test", "--", f"@{module.name}//...", "//projects/...", *apps]]
    apps = [f"//projects/{project}:app" for project in module.projects]
    return [["bazel", "build", APP_CONFIGS[lane], *apps]]


def run(lane: str, module: AddonModule, hosts: list[str]) -> None:
    if lane == "host" and hosts and host() not in hosts:
        print(f"{module.path}: its host lane runs on {', '.join(hosts)}, not {host()}")
        return
    for command in commands(lane, module):
        print("+", " ".join(command), flush=True)
        status = subprocess.run(command, cwd=ROOT / module.path / "examples").returncode
        if status not in (0, NO_TESTS if lane == "host" else 0):
            sys.exit(status)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=["host", *APP_CONFIGS])
    parser.add_argument("module", help="the module's directory below addons/")
    parser.add_argument(
        "--hosts", default="", help="the hosts addon.pkl limits the host lane to"
    )
    args = parser.parse_args()
    hosts = [name for name in args.hosts.split(",") if name]
    run(args.lane, AddonModule.load(Path("addons") / args.module), hosts)


if __name__ == "__main__":
    main()
