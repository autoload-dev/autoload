"""The lanes' work: the repository's own, the add-on modules' from their addon.pkl."""

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.addons.modules import all_modules, choices
from tools.addons.test_support import checkout
from tools.apps.apps import lanes as app_lanes
from tools.ci.lanes import LANES
from tools.ci.work import (
    ROOT,
    WORK,
    In,
    Work,
    addon_work,
    all_work,
    argv,
    environment,
    run,
    runs_on,
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

    def test_every_add_on_lane_has_its_work_and_each_module_its_own(self) -> None:
        work = all_work(self.root)
        # One piece runs every module of a lane, one each module alone.
        for lane in ("desktop", "android", "ios"):
            self.assertIn(f"{lane}:addons", work)
            self.assertIn(f"{lane}:addon-template", work)
        self.assertEqual(
            work["ios:addons"].steps()[0].command, "python3 -m tools.addons.lanes ios"
        )
        for name in ("desktop:addon:widget", "ios:addon:widget", "android:addon:gadget"):
            self.assertIn(name, work)

    def test_add_on_work_runs_in_the_default_profile(self) -> None:
        # Its release builds carry their configuration (examples/releases.bzl).
        work = all_work(self.root)
        for name in ("ios:addon:widget", "ios:addons", "desktop:addon:widget"):
            self.assertIsNone(work[name].bazel_profile, name)
        self.assertTrue(work["android:addon:gadget"].android)

    def test_the_manifests_name_only_lanes_ci_runs(self) -> None:
        for named in (choices()["lanes"], app_lanes()):
            with self.subTest(lanes=named):
                self.assertLessEqual(set(named), set(LANES))

    def test_names_are_unique(self) -> None:
        names = [work.name for work in (*WORK, *addon_work(self.root))]
        self.assertEqual(len(names), len(set(names)))

    def test_host_limited_work_runs_on_its_hosts(self) -> None:
        work = all_work(self.root)
        # CI's Linux job runs the desktop and Android self-tests, its macOS job the iOS one.
        for name, host in (("desktop", "linux"), ("android", "linux"), ("ios", "macos")):
            template = work[f"{name}:addon-template"]
            self.assertEqual(
                [runs_on(template, h) for h in ("linux", "macos")],
                [host == "linux", host == "macos"],
                name,
            )
        # The modules' desktop lanes choose their desktop systems themselves.
        self.assertEqual((), work["desktop:addons"].hosts)

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
        profiled = Work("z", "source-engine", ".", ("true",))
        self.assertIn(
            "export AUTOLOAD_BAZEL_PROFILE=source-engine;", argv(profiled, "true")[-1]
        )
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
            ("android", None),
            ("ios", None),
            ("source-engine", "source-engine"),
            ("test:example:petri", "source-engine"),
            ("test:bazel", None),
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
        # Skipped Android work provisions no SDK either.
        signed = Work("signed", "desktop", ".", ("true",), hosts=("macos",), android=True)
        known = {"signed": signed, "android:setup": Work("android:setup", None, ".", ())}
        with (
            mock.patch("tools.ci.work.host", return_value="linux"),
            mock.patch("subprocess.run") as process,
        ):
            run(["signed"], ROOT, known)
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
            text = task.read_text()
            for call in re.findall(r"run_work\(ctx, ([^)]*)\)", text):
                names.update(re.findall(r'"([^"]+)"', call))
        self.assertLessEqual({"format", "android:setup"}, names)
        self.assertLessEqual(names, set(all_work(ROOT)))

    def test_the_root_lint_names_every_add_on_module(self) -> None:
        command = all_work(ROOT)["lint"].steps()[0].command
        for module in all_modules(ROOT):
            self.assertIn(f"@autoload_{module.directory}//...", command)


if __name__ == "__main__":
    unittest.main()
