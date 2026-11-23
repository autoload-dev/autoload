"""The lanes' work: the repository's own, the add-on modules' from their addon.pkl."""

import re
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from tools.ci.work import (
    ROOT,
    WORK,
    Work,
    addon_work,
    all_work,
    argv,
    lanes,
    run,
    runs_on,
)

WORK_RUN = "python3 -m tools.ci.work run "


def checkout(root: Path, modules: dict[str, str]) -> None:
    """A checkout with mise.toml's pins and add-on modules naming their lanes."""
    (root / "mise.toml").write_text('[vars]\nandroid_build_tools = "35.0.0"\n')
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
            {"widget": '"host", "ios"', "gadget": '"host", "android"'},
        )

    def test_every_lane_plans_its_work_and_the_add_on_modules_lanes(self) -> None:
        planned = lanes(self.root)
        self.assertEqual(planned["docs"], ["docs"])
        self.assertIn("test:bazel", planned["host"])
        self.assertEqual(
            planned["host"][-3:],
            ["host:addon:gadget", "host:addon:widget", "host:addon-template"],
        )
        self.assertEqual(
            planned["android"][-2:], ["android:addon:gadget", "android:addon-template"]
        )
        self.assertEqual(planned["ios"][-2:], ["ios:addon:widget", "ios:addon-template"])
        # Work without a lane runs only when named.
        self.assertFalse(any("inspect:mobile" in names for names in planned.values()))

    def test_names_are_unique(self) -> None:
        names = [work.name for work in (*WORK, *addon_work(self.root))]
        self.assertEqual(len(names), len(set(names)))

    def test_host_limited_work_runs_on_its_hosts(self) -> None:
        template = next(
            work for work in addon_work(self.root) if work.name == "host:addon-template"
        )
        self.assertTrue(runs_on(template, "linux"))
        self.assertFalse(runs_on(template, "macos"))
        both = Work("x", "host", ".", ("true",), hosts=("linux", "macos"))
        self.assertTrue(runs_on(both, "macos"))

    def test_commands_run_in_mise_with_their_own_variables(self) -> None:
        plain = Work("x", "host", ".", ("true",), env=(("ANDROID_HOME", ""),))
        self.assertEqual(
            argv(plain, "bazel test //...", self.root),
            [
                "mise",
                "exec",
                "--",
                "bash",
                "-eo",
                "pipefail",
                "-c",
                "export ANDROID_HOME=''; bazel test //...",
            ],
        )
        android = Work("y", "android", ".", ("true",), android=True)
        process = argv(android, "bazel build //:app", self.root)
        self.assertEqual(process[:4], ["mise", "exec", "java", "--"])
        self.assertIn('export ANDROID_HOME="$ANDROID_SDK_ROOT"', process[-1])
        self.assertIn("export ANDROID_BUILD_TOOLS=35.0.0", process[-1])

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
    def test_hk_and_mise_run_work_that_exists(self) -> None:
        """hk.pkl's steps and mise.toml's tasks name work; a renamed piece fails here."""
        hk = (ROOT / "hk.pkl").read_text()
        names = set(re.findall(r'task\("([^"]+)"\)', hk))
        tasks = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]
        for task in tasks.values():
            run = task.get("run")
            if isinstance(run, str) and run.startswith(WORK_RUN):
                names.update(run.removeprefix(WORK_RUN).split())
        self.assertLessEqual({"lint", "test:setup", "test:bazel"}, names)
        self.assertLessEqual(names, set(all_work(ROOT)))


if __name__ == "__main__":
    unittest.main()
