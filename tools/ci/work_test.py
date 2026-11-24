"""The lanes' work: the repository's own, the add-on modules' from their addon.pkl."""

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.ci.work import (
    DOCS,
    DOCS_CHECK,
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
)


def checkout(root: Path, modules: dict[str, str]) -> None:
    """A checkout with add-on modules naming their lanes."""
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
        self.assertEqual(
            planned["desktop"][-3:],
            ["desktop:addon:gadget", "desktop:addon:widget", "desktop:addon-template"],
        )
        self.assertEqual(
            planned["android"][-2:], ["android:addon:gadget", "android:addon-template"]
        )
        self.assertEqual(planned["ios"][-2:], ["ios:addon:widget", "ios:addon-template"])
        # Work without a lane runs only when named.
        self.assertFalse(any("inspect:mobile" in names for names in planned.values()))

    def test_fast_tests_run_in_the_root_and_the_ruleset_modules_only_when_named(
        self,
    ) -> None:
        fast = all_work(self.root)["test:fast"]
        self.assertIsNone(fast.lane)
        self.assertEqual(
            [".", RULESET_DIR, DOCS], [step.directory for step in fast.steps()]
        )
        self.assertEqual(
            [FAST_TEST_COMMAND, FAST_TEST_COMMAND, DOCS_CHECK],
            [step.command for step in fast.steps()],
        )

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
        # A module whose desktop lane covers every desktop system has no host-limited work.
        (self.root / "other").mkdir()
        checkout(self.root / "other", {"anywhere": '"desktop"'})
        anywhere = next(addon_work(self.root / "other"))
        self.assertEqual((anywhere.name, anywhere.hosts), ("desktop:addon:anywhere", ()))

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
        with mock.patch("subprocess.run") as process:
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
                names.update(re.findall(r'"([^"]+)"', call))
        self.assertLessEqual({"test:setup", "test:fast", "android:setup"}, names)
        self.assertLessEqual(names, set(all_work(ROOT)))


if __name__ == "__main__":
    unittest.main()
