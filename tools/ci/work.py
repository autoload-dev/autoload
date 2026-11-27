"""
The repository's named work: the pieces that are no single Bazel command, where and how.

Each piece of work is a few shell commands, each run in a module directory. `aspect work
<name>...` runs pieces with Bazel's Python (.aspect/work.axl). CI's host jobs
(`aspect ci <host>`, .aspect/develop.axl) select their tests in Bazel and run from here
the Android SDK's setup and the add-on generator's self-test; `aspect ci source-engine`
runs `source-engine:full`.

Sections: Source engines, Work table, Execution, Command line.
"""

import argparse
import os
import shlex
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from tools.addons.modules import ROOT
from tools.setup.modules import RULESET

RULESET_DIR = RULESET.as_posix()

ANDROID_SETUP = "android:setup"

# The variable that selects the Bazel profile of the root module's commands (tools/bazel).
PROFILE = "AUTOLOAD_BAZEL_PROFILE"


class In(NamedTuple):
    """A command that runs in another directory than the rest of its work."""

    directory: str
    command: str


@dataclass(frozen=True)
class Work:
    """
    Shell commands that run in one directory, relative to the repository root, unless a
    command names its own. Android work needs the pinned SDK, NDK and Java. Work of a Bazel
    configuration other than the default names its profile, whose own server keeps that
    configuration's analysis (tools/bazel).
    """

    name: str
    directory: str
    commands: tuple[str | In, ...]
    android: bool = False
    profile: str | None = None

    def steps(self) -> list[In]:
        """Each command with the directory it runs in."""
        return [
            command if isinstance(command, In) else In(self.directory, command)
            for command in self.commands
        ]


# ==== Source engines ==========================================================


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

# The root module's tests that build an engine from source, such as the applications' that
# run in an editor built with their module (`--config=source-engine`, .bazelrc).
SOURCE_ENGINE_TESTS = "bazel test --config=source-engine -- //..."

# The Bazel profile of the source-engine work.
SOURCE_ENGINE = "source-engine"


# ==== Work table ==============================================================


# The named work. Both CI host jobs run the Android SDK's setup and the self-test
# (.aspect/develop.axl); the checks are tasks of their own.
WORK = (
    # The add-on generator's self-test: a fresh module from the template, whose tests this
    # host's CI config selects (tools/addons/selftest.py). Its declaration changes the root's
    # module graph, which would discard the analysis of the server it runs in.
    Work(
        "addon-template",
        ".",
        ("python3 -m tools.addons.selftest",),
        android=True,
        profile="addon-template",
    ),
    # Every source-engine case, the applications' included; the Source engine workflow runs
    # it with `aspect ci source-engine`.
    Work(
        "source-engine:full",
        ".",
        (
            In(RULESET_DIR, "bazel test --config=source-engine //..."),
            PATCHED_ENGINE.format(engine="stable"),
            PATCHED_ENGINE.format(engine="beta"),
            PATCHED_EDITOR,
            SOURCE_ENGINE_TESTS,
        ),
        android=True,
        profile=SOURCE_ENGINE,
    ),
    # The source-engine cases a Linux host can build, which the Source engine workflow's
    # Linux job runs with `aspect ci source-engine --host=linux`: the Android engines and
    # the applications' Linux engines. Bazel skips the iOS cases, which are incompatible
    # with Linux; the patched-engine scenario, which no Linux engine registers, is left out.
    Work(
        "source-engine:linux",
        ".",
        (In(RULESET_DIR, "bazel test --config=source-engine //..."), SOURCE_ENGINE_TESTS),
        android=True,
        profile=SOURCE_ENGINE,
    ),
    # The main source-engine cases, for a quicker local run: those not tagged
    # source_engine_extended, and the patched engine with its editor.
    Work(
        "source-engine",
        ".",
        (
            In(RULESET_DIR, "bazel test --config=source-engine-main //..."),
            PATCHED_EDITOR,
        ),
        android=True,
        profile=SOURCE_ENGINE,
    ),
    # Running Android work provisions the SDK first.
    Work(
        ANDROID_SETUP,
        ".",
        ("python3 -m tools.android.requirements", "python3 tools/android/sdk.py"),
        android=True,
    ),
    # Each module's registry test module, run in its release archive as the registry runs it,
    # and as the release workflow tests a release (tools/ci/release_archive.py). Each module
    # is a Bazel workspace of its own, so it runs only when named.
    Work("release:archives", ".", ("python3 -m tools.ci.release_archive",)),
    # The smoke applications' Android and iOS artifacts, inspected on macOS. They must be built
    # with --config=android and --config=official first, as the recipe builds them
    # (docs/internal/verification-recipes.md).
    Work(
        "inspect:mobile",
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

KNOWN = {work.name: work for work in WORK}


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
    server, which its tests share.
    """
    profile = work.profile if directory == "." else None
    exports = [f"export {PROFILE}={shlex.quote(profile)}"] if profile else []
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
    known: dict[str, Work] = KNOWN,
) -> None:
    """
    Run pieces of work in order; unknown names fail before any work starts. Android work
    provisions the SDK first.
    """
    env = environment()
    names = with_setup(list(names), known)
    require_android_environment([known[name] for name in names], env)
    for name in names:
        work = known[name]
        for step in work.steps():
            print(f"[{name}] {step.directory}$ {step.command}", flush=True)
            subprocess.run(
                argv(work, step.command, step.directory),
                cwd=root / step.directory,
                env=env,
                check=True,
            )


# ==== Command line ============================================================


def print_work() -> None:
    """List every piece of work with its directory."""
    for work in WORK:
        print(f"{work.directory:14} {work.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pieces = commands.add_parser(
        "run", help="Run pieces of work by name; without names, list them"
    )
    pieces.add_argument("names", nargs="*")
    args = parser.parse_args()
    try:
        if args.names:
            run(args.names)
        else:
            print_work()
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
