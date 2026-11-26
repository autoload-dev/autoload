"""
The repository's verification work: what each lane runs, where and how.

Each piece of work is a few shell commands, each run in a module directory.
`aspect lane <lane>` runs a lane on this host, as each of CI's jobs does; `aspect work
<name>...` runs single pieces. Both run this module with Bazel's Python (.aspect/work.axl).

The add-on modules' work comes from their addon.pkl: the same generic commands for each
module (tools/addons/lanes.py), and the add-on generator's self-test in every lane. The
source-engine lane runs in its own scheduled workflow, the others in CI.

A step may name its inputs: `run --changed-since <ref>`, as `aspect check` runs the checks
that are no Bazel targets yet (.aspect/develop.axl), skips the steps whose inputs did not
change since the merge base with the reference (tools/ci/changes.py). Lanes and named work
without the option run every step.

Sections: Applications, Checks, Ruleset tests, Add-on work, Work table, Selection,
Execution, Command line.
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

from tools.addons.modules import (
    ROOT,
    all_modules,
    choices,
    host,
    module_name,
    release_targets,
)
from tools.apps.apps import Application, applications
from tools.ci.changes import (
    Changes,
    Inputs,
    changes_since,
    files,
)
from tools.ci.lanes import LANES, PROFILE, profile
from tools.setup.modules import (
    RULESET,
    addon_modules,
    module_paths,
    registry_test_modules,
)

RULESET_DIR = RULESET.as_posix()

ANDROID_SETUP = "android:setup"


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

    @property
    def bazel_profile(self) -> str | None:
        """The profile of the work's Bazel commands: the one it names, else its lane's."""
        return self.profile or profile(self.lane)

    def steps(self) -> list[In]:
        """Each command with the directory it runs in and its inputs."""
        return [
            command
            if isinstance(command, In)
            else In(self.directory, command, self.inputs)
            for command in self.commands
        ]


# ==== Applications ============================================================


# The applications of examples/, by their app.pkl; add-on modules have lanes of their own.
APPLICATIONS = applications(ROOT)


def example_tests(application: Application) -> str:
    """The command that runs one application's own tests, below its package."""
    return f"bazel test --build_tests_only {application.package}/..."


def example_work() -> Iterator[Work]:
    """
    Each application's own tests, named on their own: in the desktop lane, or, for one that
    the source-engine lane tests, only when named, in that lane's profile.
    """
    for app in APPLICATIONS:
        name = f"test:example:{app.name}"
        command = (example_tests(app),)
        if "desktop" in app.lanes:
            yield Work(name, "desktop", ".", command)
        elif "source-engine" in app.lanes:
            yield Work(name, None, ".", command, profile="source-engine")


# The tests of the applications the source-engine lane verifies, such as those that run in
# an editor built from the engine sources with their module.
SOURCE_ENGINE_EXAMPLES = tuple(
    example_tests(app) for app in APPLICATIONS if "source-engine" in app.lanes
)


def release_tests(lane: str, suite: str) -> str:
    """
    The release builds of the applications that name a mobile lane, with their debug
    symbols, and a test suite, in one `bazel test`. Each package declares its releases as
    `<lane>_release`, which carries its own configuration (examples/releases.bzl); the
    add-on modules' lanes build their examples' (tools/addons/lanes.py).
    """
    targets = [
        target
        for app in APPLICATIONS
        if lane in app.lanes
        for target in release_targets(lane, app.package)
    ]
    return f"bazel test {' '.join(targets)} {suite}"


# ==== Checks ==================================================================


# The lint check (`--config=check`, shared.bazelrc) of a module's targets alone: its
# stamps, without the targets' outputs and other validations, such as the source-built
# engines that some tests' applications validate. Incompatible targets are skipped.
LINT_CHECK = "bazel build --config=check --output_groups=lint_checks --norun_validations"


def lint(root: Path = ROOT) -> In:
    """The root module's lint check, which covers the add-on modules' Python (RG027)."""
    addons = addon_modules(root)
    patterns = " ".join(f"@{module_name(Path(addon).name)}//..." for addon in addons)
    return In(".", f"{LINT_CHECK} //... {patterns}")


# What shapes the source-built engines' pins (tools/generate/generate.py): the root module's
# declarations and MODULE.bazel.lock, the ruleset's rules and extensions, and the pins themselves.
GENERATED_INPUTS = files(
    "*MODULE.bazel*",
    f"{RULESET_DIR}/godot/*.bzl",
    f"{RULESET_DIR}/godot/engine/*",
    "*.lock.json",
    "tools/generate/*",
)

# The API documentation's tests, all of them fast, with the API inventory's discovery
# of new Starlark modules, which a test's sandbox cannot see.
DOCS_CHECK = "bazel run //tools/docs:check"

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

# The workspace's own output base, which work names where its lane has another profile.
DEFAULT_PROFILE = "default"


def contracts_command(lane: str) -> str:
    """The command that checks the API output contract cases of a lane."""
    return f"bazel run //tools/docs:contracts -- --lane {lane}"


def contracts(lane: str) -> Work:
    """
    The API output contract cases of a lane. The checker builds itself and extracts the API
    in the default profile, which the docs work shares; its configured queries of the
    lane's cases run in the lane's profile (tools/docs/evidence.py). Its inputs are the docs
    work's, since the cases evaluate the same API and generated repositories.
    """
    return Work(
        f"contracts:{lane}",
        lane,
        ".",
        (contracts_command(lane),),
        android=lane == "android",
        profile=DEFAULT_PROFILE,
        inputs=DOCS_INPUTS,
    )


# ==== Ruleset tests ===========================================================


# The ruleset's consumer scenarios, by package.
SCENARIOS = "//e2e/rules_godot"

PATCHED_ENGINE = (
    f"bazel test {SCENARIOS}/patched_engine/tests:app_runs_patched_engine_test"
    f" {SCENARIOS}/patched_engine/tests:app_build_profile_test"
    f" --extra_toolchains={SCENARIOS}/patched_engine/engines/{{engine}}:all"
)

PATCHED_EDITOR = (
    f"bazel test {SCENARIOS}/patched_engine/tests:app_runs_patched_engine_test"
    f" {SCENARIOS}/patched_engine/tests:source_built_editor_test"
    f" --extra_toolchains={SCENARIOS}/patched_engine/engines/source:all"
)


# ==== Add-on work =============================================================


# The profile of the add-on generator's self-test, which changes the root's module graph.
TEMPLATE_PROFILE = "addon-template"


def lane_addon_work(lane: str) -> Work:
    """Every add-on module of a lane, with one Bazel command."""
    return Work(
        f"{lane}:addons",
        lane,
        ".",
        (f"python3 -m tools.addons.lanes {lane}",),
        android=lane == "android",
    )


def module_work(lane: str, directory: str) -> Work:
    """One add-on module's lane alone, run only when named."""
    return Work(
        f"{lane}:addon:{directory}",
        None,
        ".",
        (f"python3 -m tools.addons.lanes {lane} {directory}",),
        android=lane == "android",
    )


def template_work(lane: str) -> Work:
    """The add-on generator's self-test in one lane: a fresh module, then its lane."""
    return Work(
        f"{lane}:addon-template",
        lane,
        ".",
        (f"python3 -m tools.addons.selftest {lane}",),
        android=lane == "android",
        hosts=("linux",) if lane == "desktop" else (),
        # The self-test declares a module in the root's module graph for its run, which
        # would discard the analysis of the server it runs in.
        profile=TEMPLATE_PROFILE,
    )


def addon_work(root: Path = ROOT) -> Iterator[Work]:
    """
    The add-on modules' work: in each lane, one piece for every module whose addon.pkl names
    the lane, a single Bazel command for all of them (tools/addons/lanes.py); one piece per
    module and lane, `<lane>:addon:<module>`, for running a module alone; then the
    generator's self-test in every lane. The self-test's desktop build checks the template
    the same way on every host, so its desktop lane runs on Linux only.
    """
    modules = all_modules(root)
    lanes = choices()["lanes"]
    named = {lane for module in modules for lane in module.lanes}
    yield from (lane_addon_work(lane) for lane in lanes if lane in named)
    yield from (
        module_work(lane, module.directory) for module in modules for lane in module.lanes
    )
    yield from map(template_work, lanes)


# ==== Work table ==============================================================


# The repository's own work, in the order a lane runs it. A piece without a lane runs only
# when named.
WORK = (
    # Formatting and Starlark's lint of the whole tree, as the Git hooks run them.
    Work("format", "quality", ".", ("aspect format --scope=all --severity=fail",)),
    # Python's lint check in the root module and the add-on modules; the ruleset's runs in
    # the desktop lane, and the workflows' lint is a test.
    Work("lint", "quality", ".", (lint(),)),
    # The files no lint aspect sees, across the tree: GDScript's declaration order through
    # gdlint (.gdlintrc), and the heading structure of Markdown through rumdl (.rumdl.toml).
    # Both read the checkout's files, which a test's sandbox does not hold.
    Work(
        "lint:gdscript",
        "quality",
        ".",
        ("bazel run //tools/lint:gdscript",),
        inputs=files(
            "*.gd",
            ".gdlintrc",
            "tools/lint/gdscript*",
            "tools/lint/requirements.txt",
            "tools/lint/BUILD.bazel",
        ),
    ),
    Work(
        "lint:markdown",
        "quality",
        ".",
        ("bazel run @multitool//tools/rumdl:workspace_root -- check",),
        inputs=files("*.md", ".rumdl.toml", "multitool.lock.json"),
    ),
    Work("conventions", "quality", ".", ("bazel run //tools/conventions",)),
    # The source-built engines' pins. Bazel checks the other generated files: MODULE.bazel.lock
    # in every CI command (--config=ci), the add-on modules' declarations when it loads them.
    Work(
        "generated",
        "quality",
        ".",
        ("python3 -m tools.generate.generate --check",),
        inputs=GENERATED_INPUTS,
    ),
    # The BUILD declarations that Gazelle generates (tools/gazelle): the ruleset's
    # bzl_library targets.
    Work(
        "gazelle",
        "quality",
        ".",
        ("bazel run //tools/gazelle:rules_godot_check",),
        inputs=files(
            f"{RULESET_DIR}/*.bzl",
            f"{RULESET_DIR}/*BUILD*",
            "tools/gazelle/*",
            "MODULE.bazel*",
        ),
    ),
    # The repository tooling's tests but the API documentation's, which the docs work runs;
    # the examples' and scenarios' tests run in the desktop lane.
    Work("test:tools", "quality", ".", ("bazel test -- //tools/... -//tools/docs/...",)),
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
        ("bazel test --build_tests_only //...",),
        android=True,
    ),
    # The ruleset's Python lint check, after its tests, whose analysis it reuses; the
    # quality lane has no Android NDK, which analysing every target of the ruleset needs.
    Work(
        "lint:ruleset",
        "desktop",
        RULESET_DIR,
        (f"{LINT_CHECK} //...",),
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
    # skipped. On macOS the scenario also signs its application ad hoc.
    Work(
        "test:gdextension",
        "desktop",
        ".",
        (f"bazel test {SCENARIOS}/smoke/linux/... {SCENARIOS}/smoke/macos/...",),
    ),
    *example_work(),
    contracts("android"),
    # The mobile lanes' release builds and smoke tests carry their configuration
    # (godot_configured_app), so they keep the workspace's own server.
    Work(
        "android",
        "android",
        ".",
        (release_tests("android", f"{SCENARIOS}:android"),),
        android=True,
    ),
    contracts("ios"),
    Work(
        "ios",
        "ios",
        ".",
        (release_tests("ios", f"{SCENARIOS}:ios"),),
    ),
    contracts("source-engine"),
    # Every source-engine case, the applications' it verifies included. CI runs it in the
    # Source engine workflow.
    Work(
        "source-engine:full",
        "source-engine",
        ".",
        (
            In(RULESET_DIR, "bazel test --config=source-engine //..."),
            PATCHED_ENGINE.format(engine="stable"),
            PATCHED_ENGINE.format(engine="beta"),
            PATCHED_EDITOR,
            *SOURCE_ENGINE_EXAMPLES,
        ),
        android=True,
    ),
    # The main source-engine cases, for a quicker local run: those not tagged
    # source_engine_extended, and the patched engine with its editor.
    Work(
        "source-engine",
        None,
        ".",
        (
            In(RULESET_DIR, "bazel test --config=source-engine-main //..."),
            PATCHED_EDITOR,
        ),
        android=True,
        profile="source-engine",
    ),
    # Running Android work provisions the SDK first.
    Work(
        ANDROID_SETUP,
        None,
        ".",
        ("python3 -m tools.android.requirements", "python3 tools/android/sdk.py"),
        android=True,
    ),
    # Each module's registry test module, run in its release archive as the registry runs it,
    # and as the release workflow tests a release (tools/ci/release_archive.py). Each module
    # is a Bazel workspace of its own, so it runs only when named.
    Work("release:archives", None, ".", ("python3 -m tools.ci.release_archive",)),
    # The smoke applications' Android and iOS artifacts, inspected on macOS. They must be built
    # with --config=android and --config=official first, as the recipe builds them
    # (docs/internal/verification-recipes.md).
    Work(
        "inspect:mobile",
        None,
        RULESET_DIR,
        (
            (
                "bazel run //tools/platforms:validate_artifacts --"
                ' --android-sdk "$ANDROID_HOME" --android-ndk "$ANDROID_NDK_HOME"'
                ' --android-api-level "$(cd .. && python3 -m tools.android.requirements'
                ' --api-level)"'
                ' --java "${JAVA_HOME:-$(python3 ../tools/android/java.py)}/bin/java"'
                ' --build-tools "$ANDROID_BUILD_TOOLS"'
            ),
        ),
        android=True,
    ),
)


def lanes(known: dict[str, Work]) -> dict[str, list[str]]:
    """The names of each lane's work, in order."""
    planned: dict[str, list[str]] = {lane: [] for lane in LANES}
    for work in known.values():
        if work.lane is not None:
            planned[work.lane].append(work.name)
    return planned


def all_work(root: Path = ROOT) -> dict[str, Work]:
    """Every piece of work, by name: the repository's own and the add-on modules'."""
    return {work.name: work for work in (*WORK, *addon_work(root))}


# ==== Selection ===============================================================


def runs_on(work: Work, host: str) -> bool:
    """Whether a host may run this work: host-limited work runs on its hosts only."""
    return not work.hosts or host in work.hosts


def changes(ref: str | None) -> Changes | None:
    """The changes since the merge base with a reference, if one is given."""
    modules = (*module_paths(ROOT), *registry_test_modules(ROOT))
    return changes_since(ref, ROOT, modules) if ref else None


def where(step: In, steps: list[In]) -> str:
    """A step by its directory, or with its command where other steps share it."""
    alone = [s.directory for s in steps].count(step.directory) == 1
    return step.directory if alone else f"{step.directory}$ {step.command}"


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


# ==== Execution ===============================================================


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


def argv(work: Work, command: str, directory: str = ".") -> list[str]:
    """
    The process that runs one command of a piece of work in a directory, with the work's own
    variables. Android work runs with the provisioned SDK as ANDROID_HOME, which the Aspect
    CLI's environment (.aspect/config.axl) keeps empty while the SDK lacks the pinned platform.
    Commands in the root module run in the work's profile; the ruleset's keep its default
    server, which its desktop set and fast tests share.
    """
    profile = work.bazel_profile if directory == "." else None
    profile = ((PROFILE, profile),) if profile is not None else ()
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
                argv(work, step.command, step.directory),
                cwd=root / step.directory,
                env=env,
                check=True,
            )


def run_lane(lane: str, root: Path = ROOT) -> None:
    """Run a lane's work: on this host, all but the work limited to other hosts."""
    known = all_work(root)
    run(lanes(known)[lane], root, known)


# ==== Command line ============================================================


def print_work() -> None:
    """List every piece of work with its lane."""
    for name, work in all_work().items():
        print(f"{work.lane or '-':14} {name}")


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


if __name__ == "__main__":
    main()
