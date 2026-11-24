"""
The repository's verification work: what each lane runs, where and how.

Each piece of work is a few shell commands, each run in a module directory.
`aspect lane <lane>` runs a lane on this host, as each of CI's jobs does; `aspect work
<name>...` runs single pieces. Both run this module with Bazel's Python (.aspect/work.axl).

The add-on modules' work comes from their addon.pkl: the same generic commands for each
module (tools/addons/lanes.py), and the add-on generator's self-test in every lane. The
source-engine lane runs in its own scheduled workflow, the others in CI.

A step may name its inputs: `run --changed-since <ref>`, as the pre-push hook runs it, skips
the steps whose inputs did not change since the merge base with the reference
(tools/ci/changes.py). Lanes and named work without the option run every step.
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
from tools.ci.changes import (
    Changes,
    Inputs,
    changes_since,
    either,
    files,
    module_files,
)
from tools.ci.lanes import LANES
from tools.setup.modules import RULESET, module_paths

RULESET_DIR = RULESET.as_posix()
# The root module's Godot applications and the ruleset's consumer scenarios, by package.
EXAMPLES = "//examples"
SCENARIOS = "//e2e/rules_godot"
ANDROID_SETUP = "android:setup"
# The variable that selects a piece of work's Bazel profile (tools/bazel).
PROFILE = "AUTOLOAD_BAZEL_PROFILE"
# The lanes whose Bazel configuration differs from the desktop default, each a profile.
PROFILE_LANES = ("source-engine", "android", "ios")


class In(NamedTuple):
    """
    A command that runs in another directory than the rest of its work, or with other
    inputs; without inputs it always runs.
    """

    directory: str
    command: str
    inputs: Inputs | None = None


@dataclass(frozen=True)
class Work:
    """
    Shell commands that run in one directory, relative to the repository root, unless a
    command names its own. Android work needs the pinned SDK, NDK and Java; host-limited
    work runs on those hosts only. Work of a Bazel configuration other than the desktop
    default names its profile, whose own server keeps that configuration's analysis
    (tools/bazel).
    """

    name: str
    lane: str | None
    directory: str
    commands: tuple[str | In, ...]
    android: bool = False
    hosts: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    inputs: Inputs | None = None
    profile: str | None = None

    def steps(self) -> list[In]:
        """Each command with the directory it runs in and its inputs."""
        return [
            command
            if isinstance(command, In)
            else In(self.directory, command, self.inputs)
            for command in self.commands
        ]


def example_tests(name: str, config: str = "") -> str:
    """The command that runs one application's own tests, below examples/<name>/."""
    flags = f" --config={config}" if config else ""
    return f"bazel test --build_tests_only{flags} {EXAMPLES}/{name}/..."


def example(name: str) -> Work:
    """One application's own tests, in the desktop lane; add-on modules have lanes of their own."""
    return Work(f"test:example:{name}", "desktop", ".", (example_tests(name),))


# The API documentation's tests, all of them fast, with the API inventory's discovery
# of new Starlark modules, which a test's sandbox cannot see.
DOCS_CHECK = "bazel run //tools/docs:check"

# Petri's suites run in an editor built from the engine sources with its module, so the
# source-engine lane runs them; named on its own, it runs here too.
PETRI_TESTS = example_tests("petri", config="petri")


def every_module(
    command: str, root: Path = ROOT, inputs: Inputs | None = None
) -> tuple[In, ...]:
    """A command for each module of the checkout, as the setup checks discover them."""
    return tuple(In(module, command, inputs) for module in module_paths(root))


# A module's Python targets through the lint aspects (.aspect/config.axl), which see only the
# main repository's sources; the query spares `aspect lint` analysing every other target,
# such as the Android and iOS applications. Targets incompatible with this host are skipped.
LINT_COMMAND = (
    "targets=$(mktemp) && bazel query 'kind(\"py_(binary|library|test)\", //...)'"
    ' > "$targets" && { [ ! -s "$targets" ] || aspect lint --target-pattern-file="$targets"'
    " --skip_incompatible_explicit_targets; }"
)
# A module's lint runs for its own Python and the targets that hold it, and for the linters
# and their configuration, which the root module pins.
LINT_INPUTS = either(
    module_files("*.py", "BUILD", "BUILD.bazel", "*.bzl", "MODULE.bazel"),
    files(
        "pyproject.toml",
        "ty.toml",
        "tools/lint/*",
        ".aspect/config.axl",
        "MODULE.bazel",
        "MODULE.bazel.lock",
    ),
)
# What shapes the lock files and the source-built engines' pins (tools/generate/generate.py):
# the modules' declarations, the ruleset's rules and extensions, and the pins themselves.
GENERATED_INPUTS = files(
    "*MODULE.bazel*",
    "*.bazelignore",
    f"{RULESET_DIR}/godot/*.bzl",
    f"{RULESET_DIR}/godot/engine/*",
    # Files that module extensions read and the lock files record: tool and engine pins,
    # Maven and Swift package resolutions.
    "*.lock.json",
    "*maven_install.json",
    "*Package.resolved",
    "*Package.swift",
    "tools/generate/*",
)
# The API documentation: the ruleset's API, the documentation's tools and the root module's
# declarations and the Python those tools load.
DOCS_INPUTS = files(
    f"{RULESET_DIR}/godot/*",
    f"{RULESET_DIR}/MODULE.bazel*",
    f"{RULESET_DIR}/BUILD.bazel",
    f"{RULESET_DIR}/tools/*",
    "tools/docs/*",
    "tools/ci/lanes.py",
    "MODULE.bazel",
    "MODULE.bazel.lock",
    "tools/addons/*",
    "tools/code_health/*",
    "tools/conventions/*",
    "tools/setup/*",
)
# The contract checker's test of its mismatch reports.
MISMATCH_TEST_INPUTS = files(
    "tools/docs/*",
    f"{RULESET_DIR}/godot/tests/api_contracts/*",
    "tools/conventions/*",
)


def contracts_command(lane: str) -> str:
    """The command that checks the API output contract cases of a lane."""
    return f"bazel run //tools/docs:contracts -- --lane {lane}"


def contracts(lane: str) -> Work:
    """The API output contract cases of a lane."""
    return Work(
        f"contracts:{lane}",
        lane,
        ".",
        (contracts_command(lane),),
        android=lane == "android",
        profile=lane if lane in PROFILE_LANES else None,
    )


SOURCE_ENGINE_TESTS = 'attr(tags, "\\bsource_engine\\b", tests(//godot/...))'
# The fast tests of a module, which `aspect pre-push` runs in the ruleset: the unit tests
# by their size, the analysis tests by rules_testing's tag, and the few smoke tests
# (docs/internal/verification-architecture.md, "Test size").
FAST_TESTS = (
    "(attr(size, small, tests(//...))"
    ' union attr(tags, "\\b(starlark_analysis_test|smoke)\\b", tests(//...)))'
    ' except attr(tags, "\\b(manual|source_engine)\\b", tests(//...))'
)
# The query names its tests explicitly, so tests incompatible with this host, such as the
# macOS-only analysis tests on Linux, are skipped rather than rejected.
FAST_TEST_COMMAND = (
    f"bazel query '{FAST_TESTS}' | xargs bazel test --build_tests_only"
    " --skip_incompatible_explicit_targets"
)
PATCHED_ENGINE = (
    f"bazel test {SCENARIOS}/patched_engine/tests:app_runs_patched_engine_test"
    f" --extra_toolchains={SCENARIOS}/patched_engine/engines/{{engine}}:all"
)
PATCHED_EDITOR = (
    f"bazel test {SCENARIOS}/patched_engine/tests:app_runs_patched_engine_test"
    f" {SCENARIOS}/patched_engine/tests:source_built_editor_test"
    f" --extra_toolchains={SCENARIOS}/patched_engine/engines/source:all"
)
# The example packages with an `app`, which the mobile lanes build.
APP_PACKAGES = (
    f"{EXAMPLES}/addons/sqlite",
    f"{EXAMPLES}/lichtpost",
    f"{EXAMPLES}/addons/platform_paths",
    f"{EXAMPLES}/addons/app_auth",
)
# The Android release bundles leave Lichtpost out.
ANDROID_RELEASE_PACKAGES = tuple(p for p in APP_PACKAGES if p != f"{EXAMPLES}/lichtpost")


def apps(packages: Iterable[str], symbols: bool = False) -> str:
    """The packages' apps as Bazel targets, with their debug symbols if asked."""
    suffixes = (":app", ":app.debug_symbols") if symbols else (":app",)
    return " ".join(package + suffix for package in packages for suffix in suffixes)


# The repository's own work, in the order a lane runs it. A piece without a lane runs only
# when named.
WORK = (
    # Formatting and Starlark's lint of the whole tree, as the Git hooks run them.
    Work("format", "quality", ".", ("aspect format --scope=all --severity=fail",)),
    # The lint aspects in every module; the workflows' lint is a test.
    Work("lint", "quality", ".", every_module(LINT_COMMAND, inputs=LINT_INPUTS)),
    Work("conventions", "quality", ".", ("bazel run //tools/conventions",)),
    # The generated files: lock files and the source-built engines' pins.
    Work(
        "generated",
        "quality",
        ".",
        ("python3 -m tools.generate.generate --check",),
        inputs=GENERATED_INPUTS,
    ),
    Work(
        "test:setup",
        "quality",
        ".",
        (
            "python3 -m tools.android.requirements",
            "python3 -m tools.setup.pins",
        ),
    ),
    # The repository tooling's tests but the API documentation's, which the docs work runs;
    # the examples' and scenarios' tests run in the desktop lane.
    Work("test:tools", "quality", ".", ("bazel test -- //tools/... -//tools/docs/...",)),
    # The ruleset's fast tests.
    Work("test:fast", None, RULESET_DIR, (FAST_TEST_COMMAND,)),
    # The API inventory and the documentation of its public entrypoints, and the contract
    # cases that need no SDK.
    Work(
        "docs",
        "docs",
        ".",
        (
            DOCS_CHECK,
            contracts_command("docs"),
            In(
                ".",
                "bazel run //tools/docs:evaluated_mismatch_test",
                MISMATCH_TEST_INPUTS,
            ),
        ),
        inputs=DOCS_INPUTS,
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
    # The scenarios' desktop set needs no Android SDK or NDK; an accidental dependency fails
    # here.
    Work(
        "test:regressions",
        "desktop",
        ".",
        (f"bazel test {SCENARIOS}/...",),
        env=(("ANDROID_HOME", ""), ("ANDROID_NDK_HOME", "")),
    ),
    # Each desktop smoke scenario is compatible with its own host only; the other is
    # skipped. On macOS the scenario also runs ad hoc signed.
    Work(
        "test:gdextension",
        "desktop",
        ".",
        (f"bazel test {SCENARIOS}/smoke/linux/... {SCENARIOS}/smoke/macos/...",),
    ),
    Work(
        "test:gdextension:signed",
        "desktop",
        ".",
        (
            (
                f"bazel test {SCENARIOS}/smoke/macos/..."
                " --@autoload_rules_godot//godot:macos_signing=adhoc"
            ),
        ),
        hosts=("macos",),
    ),
    example("lichtpost"),
    contracts("android"),
    Work(
        "android",
        "android",
        ".",
        (
            f"bazel test {SCENARIOS}:android_aab --config=android --config=aab",
            f"bazel build {apps(APP_PACKAGES)} --config=android",
            (f"bazel build {EXAMPLES}/addons/sqlite:app --config=multi_abi --config=aab"),
            (
                f"bazel build {apps(ANDROID_RELEASE_PACKAGES, symbols=True)}"
                " --config=android-release --config=aab"
            ),
        ),
        android=True,
        profile="android",
    ),
    contracts("ios"),
    Work(
        "ios",
        "ios",
        ".",
        (
            f"bazel test {SCENARIOS}:ios_official --config=official",
            f"bazel build {apps(APP_PACKAGES, symbols=True)} --config=ios-release",
        ),
        profile="ios",
    ),
    contracts("source-engine"),
    # Every source-engine case, Petri's included. CI runs it in the Source engine workflow.
    Work(
        "source-engine:full",
        "source-engine",
        ".",
        (
            In(RULESET_DIR, f"bazel query '{SOURCE_ENGINE_TESTS}' | xargs bazel test"),
            PATCHED_ENGINE.format(engine="stable"),
            PATCHED_ENGINE.format(engine="beta"),
            PATCHED_EDITOR,
            PETRI_TESTS,
        ),
        android=True,
        profile="source-engine",
    ),
    # The main source-engine cases, for a quicker local run: those not tagged
    # source_engine_extended, and the patched engine with its editor.
    Work(
        "source-engine",
        None,
        ".",
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
        profile="source-engine",
    ),
    Work("test:example:petri", None, ".", (PETRI_TESTS,), profile="source-engine"),
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
                ' --android-api-level "$(cd .. && python3 -m tools.android.requirements'
                ' --api-level .)"'
                ' --java "${JAVA_HOME:-$(python3 ../tools/android/java.py)}/bin/java"'
                ' --build-tools "$ANDROID_BUILD_TOOLS"'
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
                profile=lane if lane in PROFILE_LANES else None,
            )
    yield from map(template_work, ADDON_LANES)


def template_work(lane: str) -> Work:
    """The add-on generator's self-test in one lane: a fresh module, then its lane."""
    return Work(
        f"{lane}:addon-template",
        lane,
        ".",
        (f"python3 -m tools.addons.selftest {lane}",),
        android=lane == "android",
        hosts=("linux",) if lane == "desktop" else (),
        profile=lane if lane in PROFILE_LANES else None,
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


def argv(work: Work, command: str) -> list[str]:
    """
    The process that runs one command of a piece of work, with the work's own variables.
    Android work runs with the provisioned SDK as ANDROID_HOME, which the Aspect CLI's
    environment (.aspect/config.axl) keeps empty while the SDK lacks the pinned platform.
    """
    profile = ((PROFILE, work.profile),) if work.profile is not None else ()
    exports = [
        f"export {name}={shlex.quote(value)}" for name, value in (*work.env, *profile)
    ]
    if work.android:
        exports.insert(0, 'export ANDROID_HOME="$ANDROID_SDK_ROOT"')
    script = "; ".join([*exports, command])
    return ["bash", "-eo", "pipefail", "-c", script]


def environment() -> dict[str, str]:
    """
    The work's environment: this process's, with this Python first on PATH, so the work's
    `python3` is the interpreter that runs this module, Bazel's when the Aspect CLI runs it.
    """
    path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
    return {**os.environ, "PATH": path}


def selected(work: Work, changes: Changes | None) -> list[In]:
    """
    The steps of a piece of work to run: all of them without changes, else those without
    inputs or whose inputs changed. Each skipped step is reported.
    """
    steps = work.steps()
    if changes is None:
        return steps
    chosen = []
    for step in steps:
        if step.inputs is None or step.inputs(changes, step.directory):
            chosen.append(step)
        else:
            print(
                f"[{work.name}] {where(step, steps)} skipped: no change since {changes.base}"
            )
    return chosen


def where(step: In, steps: list[In]) -> str:
    """A step by its directory, or with its command where other steps share it."""
    alone = [s.directory for s in steps].count(step.directory) == 1
    return step.directory if alone else f"{step.directory}$ {step.command}"


def with_setup(names: list[str], known: dict[str, Work]) -> list[str]:
    """The work to run, the Android SDK's setup first where Android work needs it."""
    if unknown := [name for name in names if name not in known]:
        raise ValueError(f"No such work: {', '.join(unknown)}")
    if ANDROID_SETUP not in names and any(known[name].android for name in names):
        return [ANDROID_SETUP, *names]
    return names


def require_android_environment(work: list[Work], env: dict[str, str]) -> None:
    """Android work needs the SDK the Aspect CLI selects (.aspect/config.axl)."""
    if any(piece.android for piece in work) and not env.get("ANDROID_SDK_ROOT"):
        raise ValueError("Android work needs the Android environment: run `aspect work`")


def run(
    names: Iterable[str],
    root: Path = ROOT,
    known: dict[str, Work] | None = None,
    changes: Changes | None = None,
) -> None:
    """
    Run pieces of work in order; unknown names fail before any work starts, and work
    limited to other hosts is skipped. Android work provisions the SDK first. With
    changes, only the selected steps run.
    """
    known = known or all_work(root)
    here = host()
    env = environment()
    names = with_setup(list(names), known)
    require_android_environment([known[name] for name in names], env)
    for name in names:
        work = known[name]
        if not runs_on(work, here):
            print(f"[{name}] skipped: runs on {', '.join(work.hosts)} only", flush=True)
            continue
        for step in selected(work, changes):
            print(f"[{name}] {step.directory}$ {step.command}", flush=True)
            subprocess.run(
                argv(work, step.command), cwd=root / step.directory, env=env, check=True
            )


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
    pieces.add_argument(
        "--changed-since",
        metavar="REF",
        help="skip the steps whose inputs did not change since the merge base with REF",
    )
    args = parser.parse_args()
    try:
        if args.command == "lane":
            run_lane(args.lane)
        elif args.names:
            run(args.names, changes=changes(args.changed_since))
        else:
            print_work()
    except ValueError as error:
        parser.error(str(error))


def changes(ref: str | None) -> Changes | None:
    """The changes since the merge base with a reference, if one is given."""
    return changes_since(ref, ROOT, module_paths(ROOT)) if ref else None


def print_work() -> None:
    """List every piece of work with its lane."""
    for name, work in all_work().items():
        print(f"{work.lane or '-':14} {name}")


if __name__ == "__main__":
    main()
