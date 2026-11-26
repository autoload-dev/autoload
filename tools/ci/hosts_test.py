"""CI's host jobs: the lanes of one kind of machine in a few Bazel commands."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.addons.test_support import checkout
from tools.ci.hosts import HOST_LANES, root_steps, ruleset_steps, run, selftests
from tools.ci.lanes import LANES


class HostsTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        checkout(
            self.root,
            {"widget": '"desktop", "ios"', "gadget": '"desktop", "android"'},
        )
        for module in ("widget", "gadget"):
            project = self.root / "examples/addons" / module / "project.godot"
            project.parent.mkdir(parents=True)
            project.touch()

    def commands(self, host: str) -> list[str]:
        return [step.command for step in root_steps(host, self.root)]

    def test_every_lane_but_the_scheduled_one_runs_on_a_host(self) -> None:
        covered = {lane for lanes in HOST_LANES.values() for lane in lanes}
        self.assertEqual(covered, set(LANES) - {"source-engine"})

    def test_linux_lints_then_tests_the_tooling_then_everything_else_together(
        self,
    ) -> None:
        lint, own, together = self.commands("linux")
        self.assertIn("--output_groups=lint_checks", lint)
        self.assertIn("@autoload_widget//...", lint)
        self.assertEqual(own, "bazel test --build_tests_only //tools/...")
        self.assertIn("//e2e/rules_godot/...", together)
        self.assertIn("//e2e/rules_godot:android", together)
        self.assertIn("@autoload_gadget//...", together)
        self.assertNotIn("ios", together)

    def test_macos_tests_its_desktop_and_ios_without_the_quality_lane(self) -> None:
        commands = self.commands("macos")
        self.assertEqual(len(commands), 2)
        together = commands[-1]
        self.assertIn("//e2e/rules_godot:ios", together)
        self.assertIn("@autoload_widget//...", together)
        self.assertNotIn("android", together)
        self.assertNotIn("//tools/...", commands[0])

    def test_both_hosts_test_and_lint_the_ruleset(self) -> None:
        commands = [step.command for step in ruleset_steps()]
        self.assertEqual(commands[0], "bazel test --build_tests_only //...")
        self.assertIn("--output_groups=lint_checks", commands[1])

    def test_each_host_runs_the_self_tests_of_its_lanes(self) -> None:
        self.assertEqual(
            selftests("linux", self.root),
            ["desktop:addon-template", "android:addon-template"],
        )
        # The template's desktop build is the same on every host, so Linux runs it.
        self.assertEqual(selftests("macos", self.root), ["ios:addon-template"])

    def test_a_failing_server_stops_the_job_before_the_self_tests(self) -> None:
        with (
            mock.patch.dict("os.environ", {"ANDROID_SDK_ROOT": "/sdk"}),
            mock.patch("tools.ci.hosts.run_work") as work,
            mock.patch("tools.ci.hosts.run_steps", side_effect=[0, 1]),
        ):
            self.assertEqual(run("macos", self.root), 1)
        work.assert_called_once_with(["android:setup"], self.root)


if __name__ == "__main__":
    unittest.main()
