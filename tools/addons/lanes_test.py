"""Every add-on module's lanes run the same commands over its examples in the root module."""

import unittest
from pathlib import Path

from tools.addons.lanes import command, lane_tests_query
from tools.addons.modules import AddonModule


def module(*projects: str) -> AddonModule:
    return AddonModule(Path("addons/widget"), "autoload_widget", projects)


class LanesTest(unittest.TestCase):
    def test_desktop_tests_the_module_and_every_example_target_but_the_apps(self) -> None:
        self.assertEqual(
            command("desktop", module("demo", "store")),
            [
                "bazel",
                "test",
                "--",
                "@autoload_widget//...",
                "//examples/addons/widget/...",
                "-//examples/addons/widget/projects/demo:app",
                "-//examples/addons/widget/projects/store:app",
            ],
        )

    def test_desktop_lane_of_a_module_without_application_lanes_tests_all_its_examples(
        self,
    ) -> None:
        widget = AddonModule(
            Path("addons/widget"),
            "autoload_widget",
            ("demo",),
            lanes=("desktop",),
        )
        self.assertEqual(
            command("desktop", widget),
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
            command("ios", module("demo")),
            [
                "bazel",
                "build",
                "--config=ios_sim",
                "//examples/addons/widget/projects/demo:app",
            ],
        )
        self.assertEqual(command("android", module("demo"))[2], "--config=android")

    def test_mobile_lanes_run_the_tests_tagged_with_their_name(self) -> None:
        self.assertEqual(
            command(
                "ios", module("demo"), ["//examples/addons/widget/projects/demo:app_test"]
            ),
            [
                "bazel",
                "test",
                "--config=ios_sim",
                "--",
                "//examples/addons/widget/projects/demo:app",
                "//examples/addons/widget/projects/demo:app_test",
            ],
        )
        self.assertEqual(
            lane_tests_query("android", module("demo"))[-1],
            'attr(tags, "[\\[ ]android[,\\]]",'
            " tests(//examples/addons/widget/projects/...))",
        )

    def test_a_module_without_example_projects_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            command("desktop", module())


if __name__ == "__main__":
    unittest.main()
