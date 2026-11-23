"""
The repository's verification work: what each lane runs, where and how.

Each piece of work is a few shell commands in one module directory. CI's plan
(tools/ci/verification.py) assigns every lane's work to its jobs; locally,
`python3 -m tools.ci.work lane <lane>` (`mise run lane -- <lane>`) runs a lane on this
host and `python3 -m tools.ci.work run <name>...` runs single pieces. The add-on modules'
work comes from their addon.pkl: the same generic commands for each module
(tools/addons/lanes.py), and the add-on generator's self-test in every lane.
"""

import argparse
import platform
import subprocess
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from tools.addons.modules import HOSTS as ADDON_HOSTS
from tools.addons.modules import LANES as ADDON_LANES
from tools.addons.modules import all_modules
from tools.setup.modules import RULESET

ROOT = Path(__file__).resolve().parents[2]

LANES = ("quality", "docs", "host", "source-engine", "android", "ios")
# The lanes that need a machine of their own, each with API contract cases: contracts:<lane>.
CONTRACT_LANES = ("host", "source-engine", "android", "ios")

RULESET_DIR = RULESET.as_posix()
EXAMPLES = f"{RULESET_DIR}/examples"
REGRESSIONS = f"{RULESET_DIR}/tests"


@dataclass(frozen=True)
class Work:
    """
    Shell commands that run in one directory, relative to the repository root. Android
    work needs the pinned SDK, NDK and Java; host-limited work runs on those hosts only.
    """

    name: str
    lane: str | None
    directory: str
    commands: tuple[str, ...]
    android: bool = False
    hosts: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()


def example(name: str, area: str = "addons") -> Work:
    """One example's own tests, below its directory in the examples module."""
    return Work(
        f"test:example:{name}",
        "host",
        EXAMPLES,
        (f"bazel test --build_tests_only //{area}/{name}/...",),
    )


def contracts(lane: str, android: bool = False) -> Work:
    """The API output contract cases of a lane."""
    return Work(
        f"contracts:{lane}",
        lane,
        RULESET_DIR,
        (f"bazel run //tools/docs:contracts -- --lane {lane}",),
        android=android,
    )


SOURCE_ENGINE_TESTS = 'attr(tags, "\\bsource_engine\\b", tests(//godot/...))'
PATCHED_ENGINE = (
    "bazel test //patched_engine/tests:app_runs_patched_engine_test"
    " --extra_toolchains=//patched_engine/engines/{engine}:all"
)
PATCHED_EDITOR = (
    "bazel test //patched_engine/tests:app_runs_patched_engine_test"
    " //patched_engine/tests:source_built_editor_test"
    " --extra_toolchains=//patched_engine/engines/source:all"
)
IOS_APPS = (
    "//addons/sqlite/demo:app //addons/sqlite/demo:app.debug_symbols"
    " //projects/lichtpost:app //projects/lichtpost:app.debug_symbols"
    " //addons/platform_paths/demo:app //addons/platform_paths/demo:app.debug_symbols"
    " //addons/app_auth/demo:app //addons/app_auth/demo:app.debug_symbols"
)
ANDROID_APPS = (
    "//addons/sqlite/demo:app //projects/lichtpost:app"
    " //addons/platform_paths/demo:app //addons/app_auth/demo:app"
)
ANDROID_RELEASE_APPS = (
    "//addons/sqlite/demo:app //addons/sqlite/demo:app.debug_symbols"
    " //addons/platform_paths/demo:app //addons/platform_paths/demo:app.debug_symbols"
    " //addons/app_auth/demo:app //addons/app_auth/demo:app.debug_symbols"
)

# The repository's own work, in the order a lane runs it. A piece without a lane runs only
# when named.
WORK = (
    Work(
        "lint",
        "quality",
        ".",
        (
            "bazel run --config=host-execution //tools/format:format.check",
            "bazel run --config=host-execution //tools/lint",
            "hk validate",
        ),
    ),
    Work(
        "lint:ci",
        "quality",
        ".",
        (
            "mise exec jactionlint -- jactionlint --shellcheck= --pyflakes=",
            "mise exec node -- node --test .github/actions/setup/stop-bazel/post.test.js",
        ),
    ),
    Work("conventions", "quality", ".", ("bazel run //tools/conventions",)),
    Work(
        "test:setup",
        "quality",
        ".",
        (
            "python3 -m tools.android.requirements",
            "python3 -m tools.setup.pins",
            (
                "python3 -m unittest tools.android.mise_test tools.android.requirements_test"
                " tools.setup.modules_test tools.setup.pins_test tools.addons.new_test"
                " tools.addons.lanes_test"
            ),
        ),
    ),
    Work("test:tools", "quality", ".", ("bazel test //...",)),
    Work(
        "docs",
        "docs",
        RULESET_DIR,
        (
            "bazel run //tools/docs:check",
            "bazel run //tools/docs:contracts -- --lane docs",
            "bazel run //tools/docs:evaluated_mismatch_test",
        ),
    ),
    contracts("host"),
    # The ruleset's host set, including its Android packaging tests; tests that build an
    # engine from source run in the source-engine lane.
    Work(
        "test:bazel",
        "host",
        RULESET_DIR,
        (
            (
                "bazel test --build_tests_only --test_tag_filters=-source_engine"
                " -- //... -//docs/... -//tools/docs/..."
            ),
        ),
        android=True,
    ),
    # The regression module's host set needs no Android SDK or NDK; an accidental dependency
    # fails here.
    Work(
        "test:regressions",
        "host",
        REGRESSIONS,
        ("bazel test //...",),
        env=(("ANDROID_HOME", ""), ("ANDROID_NDK_HOME", "")),
    ),
    # Each desktop smoke scenario is compatible with its own host only; the other is
    # skipped. On macOS the scenario also runs ad hoc signed.
    Work(
        "test:gdextension",
        "host",
        REGRESSIONS,
        (
            "bazel test //smoke/linux/... //smoke/macos/...",
            (
                'if [ "$(uname -s)" = Darwin ]; then bazel test //smoke/macos/...'
                " --@autoload_rules_godot//godot:macos_signing=adhoc; fi"
            ),
        ),
    ),
    example("sqlite"),
    example("lichtpost", "projects"),
    example("platform_paths"),
    example("app_auth"),
    example("dart"),
    contracts("android", android=True),
    Work(
        "android",
        "android",
        REGRESSIONS,
        (
            "bazel test //:android_aab --config=android --config=aab",
            f"cd ../examples && bazel build {ANDROID_APPS} --config=android",
            (
                "cd ../examples && bazel build //addons/sqlite/demo:app"
                " --config=multi_abi --config=aab"
            ),
            (
                f"cd ../examples && bazel build {ANDROID_RELEASE_APPS}"
                " --config=android-release --config=aab"
            ),
        ),
        android=True,
    ),
    contracts("ios"),
    Work(
        "ios",
        "ios",
        REGRESSIONS,
        (
            "bazel test //:ios_official --config=official",
            f"cd ../examples && bazel build {IOS_APPS} --config=ios-release",
        ),
    ),
    contracts("source-engine"),
    # Every source-engine case, Petri's included. CI runs it in the Source engine workflow.
    Work(
        "source-engine:full",
        "source-engine",
        REGRESSIONS,
        (
            f"cd .. && bazel query '{SOURCE_ENGINE_TESTS}' | xargs bazel test",
            PATCHED_ENGINE.format(engine="stable"),
            PATCHED_ENGINE.format(engine="beta"),
            PATCHED_EDITOR,
            (
                "cd ../examples && bazel test --build_tests_only --config=petri"
                " //projects/petri/..."
            ),
        ),
        android=True,
    ),
    # The main source-engine cases, for a quicker local run: those not tagged
    # source_engine_extended, and the patched engine with its editor.
    Work(
        "source-engine",
        None,
        REGRESSIONS,
        (
            (
                f"cd .. && bazel query '{SOURCE_ENGINE_TESTS} except"
                ' attr(tags, "\\bsource_engine_extended\\b", tests(//godot/...))\''
                " | xargs bazel test"
            ),
            PATCHED_EDITOR,
        ),
        android=True,
    ),
    # Already built Android and iOS artifacts, inspected on macOS.
    Work(
        "inspect:mobile",
        None,
        RULESET_DIR,
        (
            (
                "bazel run //tools/platforms:validate_artifacts --"
                ' --android-sdk "$ANDROID_HOME" --android-ndk "$ANDROID_NDK_HOME"'
                ' --java "$JAVA_HOME/bin/java" --build-tools "$ANDROID_BUILD_TOOLS"'
            ),
        ),
        android=True,
    ),
)


def addon_work(root: Path = ROOT) -> Iterator[Work]:
    """
    Each add-on module's lanes, as its addon.pkl names them, then the generator's self-test
    in every lane. The self-test's desktop build does the same on every host, so its host
    lane runs on Linux only.
    """
    for module in all_modules(root):
        for lane in module.lanes:
            yield Work(
                f"{lane}:addon:{module.directory}",
                lane,
                ".",
                (f"python3 -m tools.addons.lanes {lane} {module.directory}",),
                android=lane == "android",
                hosts=module.hosts if lane == "host" else (),
            )
    for lane in ADDON_LANES:
        pin = "" if lane == "android" else " --no-pin"
        yield Work(
            f"{lane}:addon-template",
            lane,
            ".",
            (
                f"python3 -m tools.addons.new .selftest{pin}",
                f"python3 -m tools.addons.lanes {lane} .selftest",
            ),
            android=lane == "android",
            hosts=("linux",) if lane == "host" else (),
        )


def all_work(root: Path = ROOT) -> dict[str, Work]:
    """Every piece of work, by name: the repository's own and the add-on modules'."""
    return {work.name: work for work in (*WORK, *addon_work(root))}


def lanes(root: Path = ROOT) -> dict[str, list[str]]:
    """The names of each lane's work, in order."""
    planned: dict[str, list[str]] = {lane: [] for lane in LANES}
    for work in all_work(root).values():
        if work.lane is not None:
            planned[work.lane].append(work.name)
    return planned


def runs_on(work: Work, host: str) -> bool:
    """Whether a host may run this work: host-limited work runs on its hosts only."""
    return not work.hosts or set(work.hosts) == set(ADDON_HOSTS) or host in work.hosts


def this_host() -> str:
    """This machine, as the lanes name hosts."""
    return {"Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system())


def mise_vars(root: Path = ROOT) -> dict[str, str]:
    """The pins of mise.toml's [vars]."""
    return tomllib.loads((root / "mise.toml").read_text())["vars"]


# Android work runs with the pinned Java and the provisioned SDK as ANDROID_HOME, which
# mise's environment keeps empty while the SDK lacks the pinned platform.
ANDROID_SETUP = (
    "python3 -m tools.android.requirements",
    "python3 tools/android/sdk.py",
)


def argv(work: Work, command: str, root: Path = ROOT) -> list[str]:
    """
    The process that runs one command of a piece of work: in mise's environment, with the
    work's own variables, which mise's would otherwise override.
    """
    exports = [f"export {name}={value!r}" for name, value in work.env]
    tools = []
    if work.android:
        tools = ["java"]
        build_tools = mise_vars(root)["android_build_tools"]
        exports[:0] = [
            'export ANDROID_HOME="$ANDROID_SDK_ROOT"',
            f"export ANDROID_BUILD_TOOLS={build_tools!r}",
        ]
    script = "; ".join([*exports, command])
    return ["mise", "exec", *tools, "--", "bash", "-euo", "pipefail", "-c", script]


def run(names: Iterable[str], root: Path = ROOT) -> None:
    """
    Run pieces of work in order; unknown names fail before any work starts. The first
    Android work provisions the SDK first.
    """
    names = list(names)
    known = all_work(root)
    if unknown := [name for name in names if name not in known]:
        raise ValueError(f"No such work: {', '.join(unknown)}")
    if any(known[name].android for name in names):
        setup = Work("android:setup", None, ".", ANDROID_SETUP, android=True)
        names = [setup.name, *names]
        known[setup.name] = setup
    for name in names:
        work = known[name]
        for command in work.commands:
            print(f"[{name}] $ {command}", flush=True)
            subprocess.run(
                argv(work, command, root), cwd=root / work.directory, check=True
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    lane = commands.add_parser("lane", help="Run one lane's work for this host")
    lane.add_argument("lane", choices=LANES)
    pieces = commands.add_parser("run", help="Run pieces of work by name")
    pieces.add_argument("names", nargs="+")
    commands.add_parser("list", help="List every piece of work by lane")
    args = parser.parse_args()
    if args.command == "list":
        for name, work in all_work().items():
            print(f"{work.lane or '-':14} {name}")
    elif args.command == "run":
        run(args.names)
    else:
        known = all_work()
        host = this_host()
        run([name for name in lanes()[args.lane] if runs_on(known[name], host)])


if __name__ == "__main__":
    main()
