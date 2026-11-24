"""
Run one lane of an add-on module, with the same commands for every module in addons/.

Each lane runs in the root module over the module's examples, examples/addons/<module>/, which
consume the module like an application:

- desktop: the module's tests, its end-to-end tests in e2e/addons/<module>/ and every target
  of its examples but the projects' apps, for the editor and this machine's desktop system,
  on the desktop systems its addon.pkl names;
- android and ios: each example project's `app`, for Android and the iOS Simulator, and the
  tests of the example projects tagged with the lane's name, such as an `ios_app_test` of
  the app; `manual` keeps them out of the desktop lane.
"""

import argparse
import subprocess
import sys

from tools.addons.modules import LANES, ROOT, AddonModule, host, module_path

# The Bazel configuration of each mobile lane, from the root module's .bazelrc.
APP_CONFIGS = {"android": "--config=android", "ios": "--config=ios_sim"}
# `bazel test` with no test among the targets exits with 4 after a successful build.
NO_TESTS = 4


def package(module: AddonModule) -> str:
    """The package of the module's examples in the root module."""
    return f"//{module.examples.as_posix()}"


def project_package(module: AddonModule, project: str) -> str:
    """The package of one example project: the examples' own, or a subdirectory's."""
    return package(module) if project == "." else f"{package(module)}/{project}"


def lane_tests_query(lane: str, module: AddonModule) -> list[str]:
    """The Bazel query for the example projects' tests that a mobile lane runs."""
    return [
        "bazel",
        "query",
        "--output=label",
        # Query renders tags as "[a, b]": match a whole element, not a tag like no-ios.
        f'attr(tags, "[\\[ ]{lane}[,\\]]", tests({package(module)}/...))',
    ]


def command(lane: str, module: AddonModule, tests: list[str] | None = None) -> list[str]:
    """The Bazel command of one lane, run in the root module, with a mobile lane's tests."""
    if not module.projects:
        raise ValueError(f"{module.path}: no example project in examples/")
    if lane == "desktop":
        apps = (
            [f"-{project_package(module, project)}:app" for project in module.projects]
            if module.builds_apps
            else []
        )
        tests = [f"//{module.tests.as_posix()}/..."] if module.end_to_end else []
        return [
            "bazel",
            "test",
            "--",
            f"@{module.name}//...",
            f"{package(module)}/...",
            *tests,
            *apps,
        ]
    apps = [f"{project_package(module, project)}:app" for project in module.projects]
    if not tests:
        return ["bazel", "build", APP_CONFIGS[lane], *apps]
    return ["bazel", "test", APP_CONFIGS[lane], "--", *apps, *tests]


def run(lane: str, module: AddonModule) -> None:
    if lane not in module.lanes:
        sys.exit(f"{module.path}: its addon.pkl names no {lane} lane")
    if lane == "desktop" and host() not in module.desktops:
        print(
            f"{module.path}: its desktop lane covers {', '.join(module.desktops)},"
            f" not {host()}"
        )
        return
    tests = None
    if lane != "desktop":
        query = lane_tests_query(lane, module)
        print("+", " ".join(query), flush=True)
        found = subprocess.run(
            query, cwd=ROOT, check=True, capture_output=True, text=True
        )
        tests = found.stdout.split()
    argv = command(lane, module, tests)
    print("+", " ".join(argv), flush=True)
    status = subprocess.run(argv, cwd=ROOT, check=False).returncode
    if status not in ({0, NO_TESTS} if lane == "desktop" else {0}):
        sys.exit(status)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=LANES)
    parser.add_argument("module", help="the module's directory below addons/")
    args = parser.parse_args()
    run(args.lane, AddonModule.load(module_path(args.module)))


if __name__ == "__main__":
    main()
