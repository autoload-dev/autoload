"""The repository's named work: what each piece runs, where and how."""

import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

from tools.ci.work import KNOWN, ROOT, WORK, In, Work, argv, environment, run


class WorkTest(unittest.TestCase):
    def test_names_are_unique(self) -> None:
        names = [work.name for work in WORK]
        self.assertEqual(len(names), len(set(names)))

    def test_commands_run_with_their_own_variables(self) -> None:
        plain = Work("x", ".", ("true",))
        self.assertEqual(
            argv(plain, "bazel test //..."),
            ["bash", "-eo", "pipefail", "-c", "bazel test //..."],
        )
        android = Work("y", ".", ("true",), android=True)
        process = argv(android, "bazel build //:app")
        self.assertIn('export ANDROID_HOME="$ANDROID_SDK_ROOT"', process[-1])
        profiled = Work("z", ".", ("true",), profile="source-engine")
        self.assertIn(
            "export AUTOLOAD_BAZEL_PROFILE=source-engine;", argv(profiled, "true")[-1]
        )
        # The ruleset's steps keep its default server.
        self.assertNotIn(
            "AUTOLOAD_BAZEL_PROFILE", argv(profiled, "true", "rules_godot")[-1]
        )

    def test_work_that_changes_the_configuration_or_module_graph_has_its_profile(
        self,
    ) -> None:
        for name, profile in (
            ("source-engine:full", "source-engine"),
            ("source-engine", "source-engine"),
            ("addon-template", "addon-template"),
        ):
            self.assertEqual(profile, KNOWN[name].profile, name)

    def test_work_runs_python_with_this_interpreter(self) -> None:
        first = environment()["PATH"].split(os.pathsep)[0]
        self.assertEqual(Path(first), Path(sys.executable).parent)

    def test_a_command_may_run_in_its_own_directory(self) -> None:
        work = Work("x", "tests", ("bazel test //:a", In("examples", "bazel build //:b")))
        self.assertEqual(
            work.steps(),
            [In("tests", "bazel test //:a"), In("examples", "bazel build //:b")],
        )
        with mock.patch("subprocess.run") as process:
            run(["x"], ROOT, {"x": work})
        self.assertEqual(
            [call.kwargs["cwd"] for call in process.call_args_list],
            [ROOT / "tests", ROOT / "examples"],
        )

    def test_android_work_provisions_the_sdk_first_and_unknown_work_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "No such work: nothing"):
            run(["release:archives", "nothing"], ROOT)
        with (
            mock.patch.dict(os.environ, {"ANDROID_SDK_ROOT": ""}),
            self.assertRaisesRegex(ValueError, "needs the Android environment"),
        ):
            run(["addon-template"], ROOT)
        with (
            mock.patch.dict(os.environ, {"ANDROID_SDK_ROOT": "/sdk"}),
            mock.patch("subprocess.run") as process,
        ):
            run(["addon-template"], ROOT)
        commands = [call.args[0][-1] for call in process.call_args_list]
        self.assertTrue(commands[0].endswith("python3 -m tools.android.requirements"))
        self.assertTrue(commands[1].endswith("python3 tools/android/sdk.py"))
        self.assertTrue(commands[2].endswith("python3 -m tools.addons.selftest"))


class CallersTest(unittest.TestCase):
    def test_aspect_tasks_run_work_that_exists(self) -> None:
        """The Aspect tasks name work; a renamed piece fails here."""
        names = set()
        for task in (ROOT / ".aspect").glob("*.axl"):
            text = task.read_text()
            for call in re.findall(r"run_work\(ctx, ([^)]*)\)", text):
                names.update(re.findall(r'"([^"]+)"', call))
        self.assertLessEqual({"android:setup", "addon-template"}, names)
        self.assertLessEqual(names, set(KNOWN))

    def test_the_source_engine_workflow_runs_the_root_s_tests_tagged_source_engine(
        self,
    ) -> None:
        # Such as Lichtpost's slim_app_build_test, whose runtime is built from source.
        commands = [step.command for step in KNOWN["source-engine:full"].steps()]
        self.assertIn("bazel test --config=source-engine -- //...", commands)


if __name__ == "__main__":
    unittest.main()
