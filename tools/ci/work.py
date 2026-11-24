"""
The repository's verification work: what each lane runs, where and how.

Each piece of work is a few shell commands, each run in a module directory.
`aspect lane <lane>` runs a lane on this host, as each of CI's jobs does; `aspect work
<name>...` runs single pieces. Both run this module with Bazel's Python (.aspect/work.axl).

The add-on modules' work comes from their addon.pkl: the same generic commands for each
module (tools/addons/lanes.py), and the add-on generator's self-test in every lane. The
source-engine lane runs in its own scheduled workflow, the others in CI.
"""

import argparse
import os
import shlex
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from tools.addons.modules import DESKTOPS, ROOT, all_modules, host
from tools.addons.modules import LANES as ADDON_LANES
from tools.setup.modules import RULESET, RULESET_DOCS

LANES = ("quality", "docs", "desktop", "source-engine", "android", "ios")
# The lanes that need a machine of their own, each with API contract cases: contracts:<lane>.
CONTRACT_LANES = ("desktop", "source-engine", "android", "ios")

RULESET_DIR = RULESET.as_posix()
EXAMPLES = f"{RULESET_DIR}/examples"
REGRESSIONS = f"{RULESET_DIR}/tests"
# The documentation module: the API documentation metadata, its checks and the contract checker.
DOCS = RULESET_DOCS.as_posix()
ANDROID_SETUP = "android:setup"


class In(NamedTuple):
    """A command that runs in another directory than the rest of its work."""

    directory: str
    command: str


@dataclass(frozen=True)
class Work:
    """
    Shell commands that run in one directory, relative to the repository root, unless a
    command names its own. Android work needs the pinned SDK, NDK and Java; host-limited
    work runs on those hosts only.
    """

    name: str
    lane: str | None
    directory: str
    commands: tuple[str | In, ...]
    android: bool = False
    hosts: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()

    def steps(self) -> list[In]:
        """Each command with the directory it runs in."""
        return [
            command if isinstance(command, In) else In(self.directory, command)
            for command in self.commands
        ]


def example_tests(name: str, area: str = "addons", config: str = "") -> str:
    """The command that runs one example's own tests, below its directory in examples/."""
    flags = f" --config={config}" if config else ""
    return f"bazel test --build_tests_only{flags} //{area}/{name}/..."


def example(name: str, area: str = "addons") -> Work:
    """One example's own tests, in the desktop lane."""
    return Work(f"test:example:{name}", "desktop", EXAMPLES, (example_tests(name, area),))


# The documentation module's tests, all of them fast, with the API inventory's discovery
# of new Starlark modules, which a test's sandbox cannot see.
DOCS_CHECK = "bazel run //tools/docs:check"

# Petri's suites run in an editor built from the engine sources with its module, so the
# source-engine lane runs them; named on its own, it runs here too.
PETRI_TESTS = example_tests("petri", "projects", config="petri")


def contracts_command(lane: str) -> str:
    """The command that checks the API output contract cases of a lane."""
    return f"bazel run //tools/docs:contracts -- --lane {lane}"


def contracts(lane: str) -> Work:
    """The API output contract cases of a lane."""
    return Work(
        f"contracts:{lane}",
        lane,
        DOCS,
        (contracts_command(lane),),
        android=lane == "android",
    )


SOURCE_ENGINE_TESTS = 'attr(tags, "\\bsource_engine\\b", tests(//godot/...))'
# The fast tests of a module, which `aspect check` runs: the unit tests by their size, the
# analysis tests by rules_testing's tag, and the few smoke tests (.aspect/tests.axl).
FAST_TEST_COMMAND = "aspect fast-test"
PATCHED_ENGINE = (
    "bazel test //patched_engine/tests:app_runs_patched_engine_test"
    " --extra_toolchains=//patched_engine/engines/{engine}:all"
)
PATCHED_EDITOR = (
    "bazel test //patched_engine/tests:app_runs_patched_engine_test"
    " //patched_engine/tests:source_built_editor_test"
    " --extra_toolchains=//patched_engine/engines/source:all"
)
# The example packages with an `app`, which the mobile lanes build.
APP_PACKAGES = (
    "//addons/sqlite/demo",
    "//projects/lichtpost",
    "//addons/platform_paths/demo",
    "//addons/app_auth/demo",
)
# The Android release bundles leave Lichtpost out.
ANDROID_RELEASE_PACKAGES = tuple(p for p in APP_PACKAGES if p != "//projects/lichtpost")


def apps(packages: Iterable[str], symbols: bool = False) -> str:
    """The packages' apps as Bazel targets, with their debug symbols if asked."""
    suffixes = (":app", ":app.debug_symbols") if symbols else (":app",)
    return " ".join(package + suffix for package in packages for suffix in suffixes)


# The repository's own work, in the order a lane runs it. A piece without a lane runs only
# when named.
WORK = (
    Work(
        "format",
        "quality",
        ".",
        ("bazel run --config=host-execution //tools/format:format.check",),
    ),
    Work("lint", "quality", ".", ("bazel run --config=host-execution //tools/lint",)),
    # The setup action's shutdown of Bazel, which runs no Bazel itself.
    Work(
        "test:actions",
        "quality",
        ".",
        (
            (
                "bazel run @multitool//tools/node:cwd --"
                " --test .github/actions/setup/stop-bazel/post.test.js"
            ),
        ),
    ),
    Work("conventions", "quality", ".", ("bazel run //tools/conventions",)),
    # The generated files: lock files and the source-built engines' pins.
    Work("generated", "quality", ".", ("python3 -m tools.generate.generate --check",)),
    Work(
        "test:setup",
        "quality",
        ".",
        (
            "python3 -m tools.android.requirements",
            "python3 -m tools.setup.pins",
            (
                "python3 -m unittest tools.android.requirements_test"
                " tools.setup.modules_test tools.setup.pins_test tools.addons.new_test"
                " tools.addons.lanes_test"
            ),
        ),
    ),
    Work("test:tools", "quality", ".", ("bazel test //...",)),
    Work(
        "test:fast",
        None,
        ".",
        (
            FAST_TEST_COMMAND,
            In(RULESET_DIR, FAST_TEST_COMMAND),
            In(DOCS, DOCS_CHECK),
        ),
    ),
    # The API inventory and the documentation of its public entrypoints, and the contract
    # cases that need no SDK.
    Work(
        "docs",
        "docs",
        DOCS,
        (
            DOCS_CHECK,
            contracts_command("docs"),
            "bazel run //tools/docs:evaluated_mismatch_test",
        ),
    ),
    contracts("desktop"),
    # The ruleset's desktop set, including its Android packaging tests; tests that build an
    # engine from source run in the source-engine lane.
    Work(
        "test:bazel",
        "desktop",
        RULESET_DIR,
        ("bazel test --build_tests_only --test_tag_filters=-source_engine //...",),
        android=True,
    ),
    # The regression module's desktop set needs no Android SDK or NDK; an accidental dependency
    # fails here.
    Work(
        "test:regressions",
        "desktop",
        REGRESSIONS,
        ("bazel test //...",),
        env=(("ANDROID_HOME", ""), ("ANDROID_NDK_HOME", "")),
    ),
    # Each desktop smoke scenario is compatible with its own host only; the other is
    # skipped. On macOS the scenario also runs ad hoc signed.
    Work(
        "test:gdextension",
        "desktop",
        REGRESSIONS,
        ("bazel test //smoke/linux/... //smoke/macos/...",),
    ),
    Work(
        "test:gdextension:signed",
        "desktop",
        REGRESSIONS,
        (
            (
                "bazel test //smoke/macos/..."
                " --@autoload_rules_godot//godot:macos_signing=adhoc"
            ),
        ),
        hosts=("macos",),
    ),
    example("sqlite"),
    example("lichtpost", "projects"),
    example("platform_paths"),
    example("app_auth"),
    example("dart"),
    contracts("android"),
    Work(
        "android",
        "android",
        REGRESSIONS,
        (
            "bazel test //:android_aab --config=android --config=aab",
            In(EXAMPLES, f"bazel build {apps(APP_PACKAGES)} --config=android"),
            In(
                EXAMPLES,
                "bazel build //addons/sqlite/demo:app --config=multi_abi --config=aab",
            ),
            In(
                EXAMPLES,
                f"bazel build {apps(ANDROID_RELEASE_PACKAGES, symbols=True)}"
                " --config=android-release --config=aab",
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
            In(
                EXAMPLES,
                f"bazel build {apps(APP_PACKAGES, symbols=True)} --config=ios-release",
            ),
        ),
    ),
    contracts("source-engine"),
    # Every source-engine case, Petri's included. CI runs it in the Source engine workflow.
    Work(
        "source-engine:full",
        "source-engine",
        REGRESSIONS,
        (
            In(RULESET_DIR, f"bazel query '{SOURCE_ENGINE_TESTS}' | xargs bazel test"),
            PATCHED_ENGINE.format(engine="stable"),
            PATCHED_ENGINE.format(engine="beta"),
            PATCHED_EDITOR,
            In(EXAMPLES, PETRI_TESTS),
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
            In(
                RULESET_DIR,
                f"bazel query '{SOURCE_ENGINE_TESTS} except"
                ' attr(tags, "\\bsource_engine_extended\\b", tests(//godot/...))\''
                " | xargs bazel test",
            ),
            PATCHED_EDITOR,
        ),
        android=True,
    ),
    Work("test:example:petri", None, EXAMPLES, (PETRI_TESTS,)),
    # Running Android work provisions the SDK first.
    Work(
        ANDROID_SETUP,
        None,
        ".",
        ("python3 -m tools.android.requirements", "python3 tools/android/sdk.py"),
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
    in every lane. The self-test's desktop build checks the template the same way on every
    host, so its desktop lane runs on Linux only.
    """
    for module in all_modules(root):
        # The desktop lane builds for this machine, so it runs on the module's desktop
        # systems; on all of them, it is no host-limited work.
        hosts = () if set(module.desktops) == set(DESKTOPS) else module.desktops
        for lane in module.lanes:
            yield Work(
                f"{lane}:addon:{module.directory}",
                lane,
                ".",
                (f"python3 -m tools.addons.lanes {lane} {module.directory}",),
                android=lane == "android",
                hosts=hosts if lane == "desktop" else (),
            )
    yield from map(template_work, ADDON_LANES)


def template_work(lane: str) -> Work:
    """The add-on generator's self-test in one lane: a fresh module, then its lane."""
    pin = "" if lane == "android" else " --no-pin"
    return Work(
        f"{lane}:addon-template",
        lane,
        ".",
        (
            f"python3 -m tools.addons.new .selftest{pin}",
            f"python3 -m tools.addons.lanes {lane} .selftest",
        ),
        android=lane == "android",
        hosts=("linux",) if lane == "desktop" else (),
    )


def all_work(root: Path = ROOT) -> dict[str, Work]:
    """Every piece of work, by name: the repository's own and the add-on modules'."""
    return {work.name: work for work in (*WORK, *addon_work(root))}


def lanes(known: dict[str, Work]) -> dict[str, list[str]]:
    """The names of each lane's work, in order."""
    planned: dict[str, list[str]] = {lane: [] for lane in LANES}
    for work in known.values():
        if work.lane is not None:
            planned[work.lane].append(work.name)
    return planned


def runs_on(work: Work, host: str) -> bool:
    """Whether a host may run this work: host-limited work runs on its hosts only."""
    return not work.hosts or host in work.hosts


# Android work's Java: the host's JAVA_HOME, or else the runtime Bazel builds with.
ANDROID_JAVA = 'export JAVA_HOME="${JAVA_HOME:-$(python3 -m tools.android.java)}"'


def argv(work: Work, command: str) -> list[str]:
    """
    The process that runs one command of a piece of work, with the work's own variables.
    Android work runs with a Java and the provisioned SDK as ANDROID_HOME, which the Aspect
    CLI's environment (.aspect/config.axl) keeps empty while the SDK lacks the pinned
    platform.
    """
    exports = [f"export {name}={shlex.quote(value)}" for name, value in work.env]
    if work.android:
        exports[:0] = ['export ANDROID_HOME="$ANDROID_SDK_ROOT"', ANDROID_JAVA]
    script = "; ".join([*exports, command])
    return ["bash", "-eo", "pipefail", "-c", script]


def environment() -> dict[str, str]:
    """
    The work's environment: this process's, with this Python first on PATH, so the work's
    `python3` is the interpreter that runs this module, Bazel's when the Aspect CLI runs it.
    """
    path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
    return {**os.environ, "PATH": path}


def with_setup(names: list[str], known: dict[str, Work]) -> list[str]:
    """The work to run, the Android SDK's setup first where Android work needs it."""
    if unknown := [name for name in names if name not in known]:
        raise ValueError(f"No such work: {', '.join(unknown)}")
    if ANDROID_SETUP not in names and any(known[name].android for name in names):
        return [ANDROID_SETUP, *names]
    return names


def run(
    names: Iterable[str], root: Path = ROOT, known: dict[str, Work] | None = None
) -> None:
    """
    Run pieces of work in order; unknown names fail before any work starts, and work
    limited to other hosts is skipped. Android work provisions the SDK first.
    """
    known = known or all_work(root)
    here = host()
    env = environment()
    for name in with_setup(list(names), known):
        work = known[name]
        if not runs_on(work, here):
            print(f"[{name}] skipped: runs on {', '.join(work.hosts)} only", flush=True)
            continue
        for directory, command in work.steps():
            print(f"[{name}] {directory}$ {command}", flush=True)
            subprocess.run(argv(work, command), cwd=root / directory, env=env, check=True)


def run_lane(lane: str, root: Path = ROOT) -> None:
    """Run a lane's work: on this host, all but the work limited to other hosts."""
    known = all_work(root)
    run(lanes(known)[lane], root, known)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    lane = commands.add_parser("lane", help="Run one lane's work for this host")
    lane.add_argument("lane", choices=LANES)
    pieces = commands.add_parser(
        "run", help="Run pieces of work by name; without names, list them by lane"
    )
    pieces.add_argument("names", nargs="*")
    args = parser.parse_args()
    try:
        if args.command == "lane":
            run_lane(args.lane)
        elif args.names:
            run(args.names)
        else:
            print_work()
    except ValueError as error:
        parser.error(str(error))


def print_work() -> None:
    """List every piece of work with its lane."""
    for name, work in all_work().items():
        print(f"{work.lane or '-':14} {name}")


if __name__ == "__main__":
    main()
