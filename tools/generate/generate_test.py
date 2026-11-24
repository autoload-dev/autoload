"""Tests of what the generators regenerate for a change, and what the check covers."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.generate import generate

RULESET_MODULES = (
    "rules_godot",
    "rules_godot/examples",
    "rules_godot/tests",
)


class GenerateTest(unittest.TestCase):
    def runs(self, call: str, *args: object) -> list[tuple[str, ...]]:
        """The Bazel commands one call of generate runs, each as (module, *arguments)."""
        with (
            mock.patch.object(generate, "bazel", return_value=0) as bazel,
            contextlib.redirect_stderr(io.StringIO()),
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

    def test_ruleset_code_regenerates_its_modules_locks(self) -> None:
        self.assertEqual(
            [(m, "mod", "deps", "--lockfile_mode=update") for m in RULESET_MODULES],
            self.runs("regenerate", ["rules_godot/godot/defs.bzl"]),
        )

    def test_the_check_covers_lock_files_and_pins(self) -> None:
        commands = self.runs("check")
        self.assertIn(
            ("rules_godot/tests", "mod", "deps", "--lockfile_mode=update"), commands
        )
        self.assertIn(
            (
                "rules_godot/examples",
                "build",
                "--nobuild",
                "--keep_going",
                "@godot_petri//toolchains:all",
            ),
            commands,
        )

    def check_lock_files(self, rewrite: str | None, *, missing: bool = False) -> int:
        """
        Check the lock files in a scratch checkout whose Bazel rewrites the ruleset's
        lock file, or none; with `missing`, the ruleset has none before.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for module in generate.LOCKED_MODULES:
                (root / module).mkdir(parents=True, exist_ok=True)
                if not (missing and module == "rules_godot"):
                    (root / module / "MODULE.bazel.lock").write_text("{}")

            def bazel(module: str, *args: str) -> int:
                if rewrite is not None and module == "rules_godot":
                    (root / module / "MODULE.bazel.lock").write_text(rewrite)
                return 0

            with (
                mock.patch.object(generate, "ROOT", root),
                mock.patch.object(generate, "bazel", side_effect=bazel),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                return generate.check_lock_files()

    def test_current_lock_files_pass_the_check(self) -> None:
        self.assertEqual(0, self.check_lock_files(rewrite=None))
        self.assertEqual(0, self.check_lock_files(rewrite="{}"))

    def test_a_lock_file_bazel_rewrites_fails_the_check(self) -> None:
        self.assertNotEqual(0, self.check_lock_files(rewrite='{"stale": false}'))

    def test_a_lock_file_bazel_writes_first_fails_the_check(self) -> None:
        self.assertNotEqual(0, self.check_lock_files(rewrite="{}", missing=True))


if __name__ == "__main__":
    unittest.main()
