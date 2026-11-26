"""Tests of what the generators regenerate for a change."""

import unittest
from unittest import mock

from tools.generate import generate

RULESET_MODULES = ("rules_godot",)


class GenerateTest(unittest.TestCase):
    def runs(self, call: str, *args: object) -> list[tuple[str, ...]]:
        """The Bazel commands one call of generate runs, each as (module, *arguments)."""
        with (
            mock.patch.object(generate, "bazel", return_value=0) as bazel,
            mock.patch.object(generate.declarations, "write"),
        ):
            getattr(generate, call)(*args)
        return [tuple(c.args) for c in bazel.call_args_list]

    def test_the_add_on_modules_are_not_locked(self) -> None:
        self.assertEqual((".", *RULESET_MODULES), generate.LOCKED_MODULES)

    def test_python_and_test_changes_regenerate_nothing(self) -> None:
        paths = ["tools/ci/work.py", "rules_godot/godot/private/tests/pack_tests.bzl"]
        self.assertEqual([], self.runs("regenerate", paths))

    def test_a_module_file_regenerates_its_own_lock_file(self) -> None:
        self.assertEqual(
            [(".", "mod", "deps", "--lockfile_mode=update")],
            self.runs("regenerate", ["MODULE.bazel"]),
        )

    def test_an_add_on_module_file_regenerates_the_root_s_lock_file(self) -> None:
        self.assertEqual(
            [(".", "mod", "deps", "--lockfile_mode=update")],
            self.runs("regenerate", ["addons/sqlite/MODULE.bazel"]),
        )

    def test_ruleset_code_regenerates_the_locks_of_its_consumers(self) -> None:
        self.assertEqual(
            [(m, "mod", "deps", "--lockfile_mode=update") for m in (".", "rules_godot")],
            self.runs("regenerate", ["rules_godot/godot/defs.bzl"]),
        )

    def test_the_add_on_declarations_are_written(self) -> None:
        with (
            mock.patch.object(generate, "bazel", return_value=0),
            mock.patch.object(generate.declarations, "write") as write,
        ):
            generate.regenerate(["tools/ci/work.py"])
        write.assert_called_once_with(generate.ROOT)


if __name__ == "__main__":
    unittest.main()
