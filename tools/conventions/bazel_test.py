"""Regressions for where the Bazel tool loads each module and how it names the module's labels."""

import unittest
from unittest.mock import patch

from tools.conventions.bazel import Bazel, Scope
from tools.conventions.context import SourceFile
from tools.conventions.test_support import RepositoryTest


def rule(name: str, path: str, labels: str = "") -> str:
    return f'<rule class="filegroup" name="{name}" location="{path}:1:1">{labels}</rule>'


class BazelTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write("addons/sqlite/MODULE.bazel", "")
        self.write("addons/sqlite/BUILD.bazel", "")
        self.write("addons/sqlite/bcr/smoke/MODULE.bazel", "")
        self.write("addons/sqlite/bcr/smoke/BUILD.bazel", "")
        self.workspace_ = self.workspace()
        self.root_module, self.addon = self.workspace_.loaded_modules
        self.bazel = Bazel(
            self.root,
            {
                self.root_module: Scope(self.root),
                self.addon: Scope(self.root, "autoload_sqlite"),
            },
        )

    def test_registry_test_modules_are_not_loaded(self) -> None:
        self.assertEqual(
            ["addons/sqlite", "."],
            sorted(
                (m.path.as_posix() for m in self.workspace_.loaded_modules), reverse=True
            ),
        )

    def test_a_workspace_loads_its_modules_in_one_query(self) -> None:
        reference = '<label name="srcs" value="@autoload_sqlite//:data"/>'
        xml = (
            "<query>"
            + rule("//:app", f"{self.root}/BUILD.bazel")
            + rule(
                "@autoload_sqlite//:lib",
                f"{self.root}/addons/sqlite/BUILD.bazel",
                reference,
            )
            + "</query>"
        )
        with patch("tools.conventions.bazel.run_tool", return_value=xml) as query:
            addon = self.bazel.rules(self.addon)
            main = self.bazel.rules(self.root_module)
        self.assertEqual(1, query.call_count)
        command, workspace = query.call_args.args
        self.assertEqual(self.root, workspace)
        self.assertEqual("kind(rule, set(//:all @autoload_sqlite//:all))", command[2])
        self.assertEqual(["//:app"], [target.label for target in main])
        # The add-on module's labels read as the module itself writes them.
        self.assertEqual(["//:lib"], [target.label for target in addon])
        self.assertEqual("//:data", addon[0].labels["srcs"])

    def test_a_module_of_its_own_loads_in_its_directory(self) -> None:
        bazel = Bazel(self.root)
        with patch("tools.conventions.bazel.run_tool", return_value="<query/>") as query:
            bazel.rules(self.addon)
        self.assertEqual(self.root / "addons/sqlite", query.call_args.args[1])

    def test_inspection_names_the_module_through_its_repository(self) -> None:
        xml = (
            '<query><source-file name="@autoload_sqlite//:data.txt"'
            f' location="{self.root}/addons/sqlite/data.txt:1:1"/></query>'
        )
        self.write("addons/sqlite/data.txt", "")
        with patch("tools.conventions.bazel.run_tool", return_value=xml) as query:
            facts = self.bazel.inspect(self.addon, ("//:data.txt",))
        self.assertEqual('set("@autoload_sqlite//:data.txt")', query.call_args.args[0][2])
        self.assertEqual(
            SourceFile("//:data.txt", self.root / "addons/sqlite/data.txt"),
            facts["//:data.txt"],
        )

    def test_dependent_tests_are_partitioned_by_module(self) -> None:
        output = "//:app_test\n@autoload_sqlite//:lib_test\n"
        with patch("tools.conventions.bazel.run_tool", return_value=output) as query:
            addon = self.bazel.dependent_tests(self.addon, ("//:godot",), ("manual",))
            main = self.bazel.dependent_tests(
                self.root_module, ("//:godot",), ("manual",)
            )
        self.assertEqual(1, query.call_count)
        self.assertIn("tests(//... + @autoload_sqlite//...)", query.call_args.args[0][2])
        self.assertEqual(frozenset({"//:lib_test"}), addon)
        self.assertEqual(frozenset({"//:app_test"}), main)


if __name__ == "__main__":
    unittest.main()
