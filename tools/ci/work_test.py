"""
The lanes' work: the repository's own, the add-on modules' from their addon.pkl.

Sections: Work and callers, Selection, Changes.
"""

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.addons.modules import choices
from tools.addons.test_support import copy_schemas
from tools.apps.apps import lanes as app_lanes
from tools.ci.changes import Changes, changes_since
from tools.ci.lanes import LANES
from tools.ci.work import (
    FAST_TEST_COMMAND,
    ROOT,
    RULESET_DIR,
    WORK,
    In,
    Work,
    addon_work,
    all_work,
    argv,
    environment,
    lanes,
    run,
    runs_on,
    selected,
)

# ==== Work and callers ========================================================


def checkout(root: Path, modules: dict[str, str]) -> None:
    """A checkout with add-on modules naming their lanes, and the schema they amend."""
    copy_schemas(root)
    for module, listed in modules.items():
        (root / "addons" / module).mkdir(parents=True)
        (root / "addons" / module / "MODULE.bazel").write_text(
            f'module(name = "autoload_{module}")\n'
        )
        (root / "addons" / module / "addon.pkl").write_text(
            f'amends "../../tools/addons/Addon.pkl"\nlanes = List({listed})\n'
        )


class WorkTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        checkout(
            self.root,
            {"widget": '"desktop", "ios"', "gadget": '"desktop", "android"'},
        )

    def test_every_lane_plans_its_work_and_the_add_on_modules_lanes(self) -> None:
        planned = lanes(all_work(self.root))
        self.assertEqual(planned["docs"], ["docs"])
        self.assertIn("test:bazel", planned["desktop"])
        # One piece runs every module of a lane; the pieces per module run when named.
        self.assertEqual(
            planned["desktop"][-2:], ["desktop:addons", "desktop:addon-template"]
        )
        self.assertEqual(
            planned["android"][-2:], ["android:addons", "android:addon-template"]
        )
        self.assertEqual(planned["ios"][-2:], ["ios:addons", "ios:addon-template"])
        self.assertEqual(
            all_work(self.root)["ios:addons"].steps()[0].command,
            "python3 -m tools.addons.lanes ios",
        )
        # Work without a lane runs only when named.
        for name in ("inspect:mobile", "desktop:addon:widget", "ios:addon:widget"):
            self.assertFalse(any(name in names for names in planned.values()), name)

    def test_a_module_s_own_work_runs_in_the_default_profile(self) -> None:
        # Its release builds carry their configuration (examples/releases.bzl).
        work = all_work(self.root)
        self.assertIsNone(work["ios:addon:widget"].bazel_profile)
        self.assertEqual("default", work["ios:addons"].bazel_profile)
        self.assertIsNone(work["desktop:addon:widget"].bazel_profile)
        self.assertTrue(work["android:addon:gadget"].android)

    def test_fast_tests_run_in_the_ruleset_only_when_named(self) -> None:
        # The root module's tests are test:tools, the API documentation's are docs.
        fast = all_work(self.root)["test:fast"]
        self.assertIsNone(fast.lane)
        self.assertEqual([In(RULESET_DIR, FAST_TEST_COMMAND)], fast.steps())

    def test_the_manifests_name_only_lanes_ci_runs(self) -> None:
        for named in (choices()["lanes"], app_lanes()):
            with self.subTest(lanes=named):
                self.assertLessEqual(set(named), set(LANES))

    def test_names_are_unique(self) -> None:
        names = [work.name for work in (*WORK, *addon_work(self.root))]
        self.assertEqual(len(names), len(set(names)))

    def test_host_limited_work_runs_on_its_hosts(self) -> None:
        template = next(
            work
            for work in addon_work(self.root)
            if work.name == "desktop:addon-template"
        )
        self.assertTrue(runs_on(template, "linux"))
        self.assertFalse(runs_on(template, "macos"))
        # The modules' desktop lanes choose their desktop systems themselves.
        self.assertEqual((), all_work(self.root)["desktop:addons"].hosts)

    def test_commands_run_with_their_own_variables(self) -> None:
        plain = Work("x", "desktop", ".", ("true",), env=(("ANDROID_HOME", ""),))
        self.assertEqual(
            argv(plain, "bazel test //..."),
            [
                "bash",
                "-eo",
                "pipefail",
                "-c",
                "export ANDROID_HOME=''; bazel test //...",
            ],
        )
        android = Work("y", "android", ".", ("true",), android=True)
        process = argv(android, "bazel build //:app")
        self.assertIn('export ANDROID_HOME="$ANDROID_SDK_ROOT"', process[-1])
        profiled = Work("z", "ios", ".", ("true",))
        self.assertIn("export AUTOLOAD_BAZEL_PROFILE=ios;", argv(profiled, "true")[-1])
        # The ruleset's steps keep its default server.
        self.assertNotIn(
            "AUTOLOAD_BAZEL_PROFILE", argv(profiled, "true", "rules_godot")[-1]
        )
        self.assertNotIn("AUTOLOAD_BAZEL_PROFILE", argv(plain, "true")[-1])

    def test_mobile_work_keeps_the_default_profile_and_source_engine_work_its_own(
        self,
    ) -> None:
        work = all_work(ROOT)
        for name, profile in (
            # Mobile applications carry their configuration (godot_configured_app).
            ("android", "default"),
            # The checker picks the lane's profile for its cases' configured queries.
            ("contracts:android", "default"),
            ("ios", "default"),
            ("contracts:ios", "default"),
            ("source-engine", "source-engine"),
            ("test:example:petri", "source-engine"),
            ("test:bazel", None),
            ("contracts:desktop", "default"),
            ("docs", None),
        ):
            self.assertEqual(profile, work[name].bazel_profile, name)

    def test_work_runs_python_with_this_interpreter(self) -> None:
        first = environment()["PATH"].split(os.pathsep)[0]
        self.assertEqual(Path(first), Path(sys.executable).parent)

    def test_a_command_may_run_in_its_own_directory(self) -> None:
        work = Work(
            "x", "ios", "tests", ("bazel test //:a", In("examples", "bazel build //:b"))
        )
        self.assertEqual(
            work.steps(),
            [In("tests", "bazel test //:a"), In("examples", "bazel build //:b")],
        )
        with mock.patch("subprocess.run") as process:
            run(["ios"], ROOT, {"ios": work})
        self.assertEqual(
            [call.kwargs["cwd"] for call in process.call_args_list],
            [ROOT / "tests", ROOT / "examples"],
        )

    def test_work_limited_to_other_hosts_is_skipped_even_when_named(self) -> None:
        signed = Work("signed", "desktop", ".", ("true",), hosts=("macos",))
        with (
            mock.patch("tools.ci.work.host", return_value="linux"),
            mock.patch("subprocess.run") as process,
        ):
            run(["signed"], ROOT, {"signed": signed})
        process.assert_not_called()

    def test_android_work_provisions_the_sdk_first_and_unknown_work_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "No such work: nothing"):
            run(["lint", "nothing"], self.root)
        with (
            mock.patch.dict(os.environ, {"ANDROID_SDK_ROOT": ""}),
            self.assertRaisesRegex(ValueError, "needs the Android environment"),
        ):
            run(["android:addon:gadget"], self.root)
        with (
            mock.patch.dict(os.environ, {"ANDROID_SDK_ROOT": "/sdk"}),
            mock.patch("subprocess.run") as process,
        ):
            run(["android:addon:gadget"], self.root)
        commands = [call.args[0][-1] for call in process.call_args_list]
        self.assertTrue(commands[0].endswith("python3 -m tools.android.requirements"))
        self.assertTrue(commands[1].endswith("python3 tools/android/sdk.py"))
        self.assertTrue(
            commands[2].endswith("python3 -m tools.addons.lanes android gadget")
        )


class CallersTest(unittest.TestCase):
    def test_aspect_tasks_run_work_that_exists(self) -> None:
        """The Aspect tasks name work; a renamed piece fails here."""
        names = set()
        for task in (ROOT / ".aspect").glob("*.axl"):
            for call in re.findall(r"run_work\(ctx, ([^)]*)\)", task.read_text()):
                # Keyword arguments, such as changed_since, name no work.
                call = re.sub(r'\w+ = "[^"]*"', "", call)
                names.update(re.findall(r'"([^"]+)"', call))
        self.assertLessEqual({"test:fast", "android:setup"}, names)
        self.assertLessEqual(names, set(all_work(ROOT)))


# ==== Selection ===============================================================


# The modules of a checkout with one add-on module, as `tools/setup/modules.py` finds them.
MODULES = (
    ".",
    "rules_godot",
    "addons/sentry",
)


def changed(*paths: str) -> Changes:
    return Changes(frozenset(paths), "abc1234", MODULES)


class SelectionTest(unittest.TestCase):
    """The pre-push hook runs only the steps whose inputs changed since the merge base."""

    def run_steps(self, name: str, *paths: str) -> list[In]:
        """The steps of a piece of work that run for the changed paths."""
        work = all_work(ROOT)[name]
        work = Work(name, work.lane, ".", tuple(self.lint_steps(work)))
        with contextlib.redirect_stdout(io.StringIO()):
            return selected(work, changed(*paths))

    def lint_steps(self, work: Work) -> list[In]:
        """A lint over the test's modules instead of the checkout's."""
        if work.name != "lint":
            return work.steps()
        step = work.steps()[0]
        return [In(module, step.command, step.inputs) for module in MODULES]

    def directories(self, name: str, *paths: str) -> list[str]:
        return [step.directory for step in self.run_steps(name, *paths)]

    def test_lint_runs_in_the_modules_with_changes(self) -> None:
        self.assertEqual(
            ["addons/sentry"], self.directories("lint", "addons/sentry/a.py")
        )
        self.assertEqual(
            ["rules_godot"], self.directories("lint", "rules_godot/tools/BUILD.bazel")
        )
        self.assertEqual(["."], self.directories("lint", "tools/BUILD.bazel"))
        # No other module imports the root module's Python.
        self.assertEqual(["."], self.directories("lint", "tools/addons/new.py"))
        self.assertEqual([], self.directories("lint"))

    def test_lint_skips_files_that_are_no_python_or_targets(self) -> None:
        self.assertEqual(
            [], self.directories("lint", "addons/sentry/README.md", "docs/a.md")
        )

    def test_a_lint_input_lints_every_module(self) -> None:
        for path in (
            "pyproject.toml",
            "ty.toml",
            "tools/lint/linters.bzl",
            "MODULE.bazel",
        ):
            self.assertEqual(list(MODULES), self.directories("lint", path))

    def test_gdscript_lint_runs_for_scripts_and_its_linter(self) -> None:
        for path in ("examples/lichtpost/main/game.gd", "tools/lint/gdscript.py"):
            self.assertEqual(["."], self.directories("lint:gdscript", path))
        self.assertEqual([], self.directories("lint:gdscript", "docs/a.md", "a.py"))

    def test_markdown_lint_runs_for_markdown_and_its_configuration(self) -> None:
        for path in ("rules_godot/docs/public/engine.md", ".rumdl.toml"):
            self.assertEqual(["."], self.directories("lint:markdown", path))
        self.assertEqual([], self.directories("lint:markdown", "a.gd", "a.py"))

    def test_generated_runs_for_what_shapes_the_engine_pins(self) -> None:
        self.assertEqual([], self.run_steps("generated", "tools/addons/new.py"))
        for path in (
            "rules_godot/MODULE.bazel",
            "MODULE.bazel.lock",
            "rules_godot/godot/defs.bzl",
            "rules_godot/godot/engine/BUILD.bazel",
            "examples/engines/simulation/simulation.lock.json",
            "tools/generate/generate.py",
        ):
            self.assertEqual(1, len(self.run_steps("generated", path)), path)

    def test_docs_check_their_inputs(self) -> None:
        commands = [
            step.command for step in self.run_steps("docs", "rules_godot/godot/defs.bzl")
        ]
        self.assertEqual(
            [
                "bazel run //tools/docs:check",
                "bazel run //tools/docs:contracts -- --lane docs",
            ],
            commands,
        )
        for path in ("rules_godot/MODULE.bazel", "tools/setup/pins.py"):
            self.assertEqual(2, len(self.run_steps("docs", path)), path)
        self.assertEqual([], self.run_steps("docs", "addons/sentry/a.py"))

    def test_desktop_contracts_check_the_docs_inputs(self) -> None:
        # The pre-push hook runs them where a change can shape the desktop cases, such as a
        # generated repository's public targets.
        for path in (
            "rules_godot/godot/engine/private/hub.bzl",
            "tools/docs/contracts.py",
        ):
            self.assertEqual(
                ["bazel run //tools/docs:contracts -- --lane desktop"],
                [step.command for step in self.run_steps("contracts:desktop", path)],
                path,
            )
        self.assertEqual([], self.run_steps("contracts:desktop", "addons/sentry/a.py"))

    def test_the_contract_checker_runs_its_own_test(self) -> None:
        for path in (
            "tools/docs/contracts.py",
            "rules_godot/godot/tests/api_contracts/cases.bzl",
            "tools/conventions/check.py",
        ):
            steps = self.run_steps("docs", path)
            self.assertEqual(
                (".", "bazel run //tools/docs:evaluated_mismatch_test"),
                steps[-1][:2],
                path,
            )

    def test_some_work_always_runs(self) -> None:
        for name in ("conventions", "test:fast", "test:tools"):
            self.assertEqual(all_work(ROOT)[name].steps(), self.run_steps(name), name)

    def test_without_changes_every_step_runs(self) -> None:
        lint = all_work(ROOT)["lint"]
        self.assertEqual(lint.steps(), selected(lint, None))

    def test_a_skipped_step_is_reported(self) -> None:
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            selected(all_work(ROOT)["docs"], changed("addons/sentry/a.py"))
        self.assertIn(
            "[docs] .$ bazel run //tools/docs:check skipped: no change since abc1234",
            printed.getvalue(),
        )
        printed = io.StringIO()
        lint = Work("lint", None, ".", tuple(self.lint_steps(all_work(ROOT)["lint"])))
        with contextlib.redirect_stdout(printed):
            selected(lint, changed("addons/sentry/a.py"))
        self.assertIn(
            "[lint] rules_godot skipped: no change since abc1234",
            printed.getvalue(),
        )


# ==== Changes =================================================================


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class ChangesTest(unittest.TestCase):
    """The changed files since the merge base with a reference, as Git reports them."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        git(self.root, "init", "--quiet", "--initial-branch=main")
        self.write("README.md", "README.md", "addons/sentry/a.py")
        git(self.root, "add", ".")
        git(self.root, "commit", "--quiet", "-m", "base")
        self.base = git(self.root, "rev-parse", "HEAD")[:9]
        git(self.root, "switch", "--quiet", "-c", "topic")

    def write(self, *paths: str) -> None:
        for path in paths:
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text(path + str(len(list(self.root.iterdir()))))

    def changes(self, ref: str = "main") -> Changes | None:
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            found = changes_since(ref, self.root, MODULES)
        self.printed = printed.getvalue()
        return found

    def test_committed_staged_unstaged_and_untracked_files_count(self) -> None:
        self.write("committed.md")
        git(self.root, "add", ".")
        git(self.root, "commit", "--quiet", "-m", "topic")
        self.write("staged.md")
        git(self.root, "add", "staged.md")
        self.write("README.md", "untracked.md")
        found = self.changes()
        assert found is not None
        self.assertEqual(
            {"committed.md", "staged.md", "README.md", "untracked.md"}, found.paths
        )
        self.assertEqual(self.base, found.base)
        self.assertEqual(MODULES, found.modules)

    def test_a_deleted_file_counts(self) -> None:
        (self.root / "addons/sentry/a.py").unlink()
        found = self.changes()
        assert found is not None
        self.assertEqual({"addons/sentry/a.py"}, found.paths)

    def test_a_renamed_file_changes_both_paths(self) -> None:
        git(self.root, "mv", "addons/sentry/a.py", "b.py")
        found = self.changes()
        assert found is not None
        self.assertEqual({"addons/sentry/a.py", "b.py"}, found.paths)

    def test_main_moving_on_changes_nothing_here(self) -> None:
        git(self.root, "switch", "--quiet", "main")
        self.write("upstream.md")
        git(self.root, "add", ".")
        git(self.root, "commit", "--quiet", "-m", "upstream")
        git(self.root, "switch", "--quiet", "topic")
        found = self.changes()
        assert found is not None
        self.assertEqual(frozenset(), found.paths)

    def test_without_a_merge_base_everything_runs(self) -> None:
        self.assertIsNone(self.changes("origin/main"))
        self.assertIn("no merge base with origin/main", self.printed)

    def test_the_verification_tooling_selects_everything(self) -> None:
        for path in (
            "tools/ci/work.py",
            ".aspect/hooks.axl",
            "shared.bazelrc",
            ".bazelversion",
            "tools/bazel",
            "rules_godot/tools/bazel",
        ):
            self.write(path)
            self.assertIsNone(self.changes(), path)
            self.assertIn(f"{path} changed", self.printed)
            (self.root / path).unlink()


if __name__ == "__main__":
    unittest.main()
