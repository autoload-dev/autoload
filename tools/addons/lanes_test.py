"""Every add-on module's lanes run the same commands over its examples in the root module."""

import contextlib
import io
import unittest
from pathlib import Path
from unittest import mock

from tools.addons.lanes import command, lane_tests_query, runnable
from tools.addons.modules import AddonModule


def module(*projects: str) -> AddonModule:
    return AddonModule(Path("addons/widget"), "autoload_widget", projects)


class LanesTest(unittest.TestCase):
    def test_desktop_tests_the_module_and_every_example_target_but_the_apps(self) -> None:
        self.assertEqual(
            command("desktop", [module("demo", "store")]),
            [
                "bazel",
                "test",
                "--",
                "@autoload_widget//...",
                "//examples/addons/widget/...",
                "-//examples/addons/widget/demo:app",
                "-//examples/addons/widget/store:app",
            ],
        )

    def test_desktop_runs_a_module_s_end_to_end_tests(self) -> None:
        widget = AddonModule(
            Path("addons/widget"), "autoload_widget", (".",), end_to_end=True
        )
        self.assertIn("//e2e/addons/widget/...", command("desktop", [widget]))

    def test_desktop_lane_of_a_module_without_application_lanes_tests_all_its_examples(
        self,
    ) -> None:
        widget = AddonModule(
            Path("addons/widget"),
            "autoload_widget",
            (".",),
            lanes=("desktop",),
        )
        self.assertEqual(
            command("desktop", [widget]),
            [
                "bazel",
                "test",
                "--",
                "@autoload_widget//...",
                "//examples/addons/widget/...",
            ],
        )

    def test_mobile_lanes_build_each_example_app(self) -> None:
        self.assertEqual(
            command("ios", [module(".")]),
            ["bazel", "build", "--config=official", "//examples/addons/widget:app"],
        )
        self.assertEqual(command("android", [module(".")])[2], "--config=android")

    def test_mobile_lanes_run_the_tests_tagged_with_their_name(self) -> None:
        self.assertEqual(
            command("ios", [module(".")], ["//examples/addons/widget:app_test"]),
            [
                "bazel",
                "test",
                "--config=official",
                "--",
                "//examples/addons/widget:app",
                "//examples/addons/widget:app_test",
            ],
        )
        self.assertEqual(
            lane_tests_query("android", [module(".")])[-1],
            'attr(tags, "[\\[ ]android[,\\]]", tests(//examples/addons/widget/...))',
        )

    def test_a_module_without_example_projects_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            command("desktop", [module()])

    def test_one_command_covers_every_module_of_a_lane(self) -> None:
        gadget = AddonModule(Path("addons/gadget"), "autoload_gadget", (".",))
        self.assertEqual(
            command("ios", [module("."), gadget]),
            [
                "bazel",
                "build",
                "--config=official",
                "//examples/addons/widget:app",
                "//examples/addons/gadget:app",
            ],
        )
        desktop = command("desktop", [module("."), gadget])
        self.assertLess(
            desktop.index("@autoload_widget//..."), desktop.index("@autoload_gadget//...")
        )
        self.assertEqual(
            lane_tests_query("ios", [module("."), gadget])[-1],
            'attr(tags, "[\\[ ]ios[,\\]]", tests(//examples/addons/widget/...'
            " + //examples/addons/gadget/...))",
        )

    def test_a_desktop_lane_runs_on_the_desktop_systems_its_module_names(self) -> None:
        linux = AddonModule(
            Path("addons/gadget"), "autoload_gadget", (".",), desktops=("linux",)
        )
        with (
            mock.patch("tools.addons.lanes.host", return_value="macos"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual([module(".")], runnable("desktop", [module("."), linux]))
        with self.assertRaises(SystemExit):
            runnable("ios", [AddonModule(Path("addons/a"), "a", (".",), lanes=())])


if __name__ == "__main__":
    unittest.main()
