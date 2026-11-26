"""Tests of what the generators regenerate for a change, and what the check covers."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.generate import generate

RULESET_MODULES = ("rules_godot",)


class GenerateTest(unittest.TestCase):
    def runs(self, call: str, *args: object) -> list[tuple[str, ...]]:
        """The Bazel commands one call of generate runs, each as (module, *arguments)."""
        mapping = {"simulation": "autoload_rules_godot++godot_engines+simulation"}
        with (
            mock.patch.object(generate, "bazel", return_value=0) as bazel,
            mock.patch.object(generate, "segment", return_value=0),
            mock.patch.object(generate, "repo_mapping", return_value=mapping),
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

    def test_an_add_on_module_file_regenerates_the_root_s_lock_file(self) -> None:
        self.assertEqual(
            [(".", "mod", "deps", "--lockfile_mode=update")],
            self.runs("regenerate", ["addons/sqlite/MODULE.bazel"]),
        )

    def test_the_segment_is_written_and_checked(self) -> None:
        with (
            mock.patch.object(generate, "bazel", return_value=0),
            mock.patch.object(generate, "repo_mapping", return_value={"simulation": "x"}),
        ):
            for call, args in (("regenerate", (["tools/ci/work.py"],)), ("check", ())):
                with (
                    self.subTest(call=call),
                    mock.patch.object(generate, "segment", return_value=0) as segment,
                ):
                    getattr(generate, call)(*args)
                    segment.assert_called_once()

    def test_ruleset_code_regenerates_the_locks_of_its_consumers(self) -> None:
        self.assertEqual(
            [(m, "mod", "deps", "--lockfile_mode=update") for m in (".", "rules_godot")],
            self.runs("regenerate", ["rules_godot/godot/defs.bzl"]),
        )

    def test_the_check_covers_lock_files_and_pins(self) -> None:
        commands = self.runs("check")
        self.assertIn(("rules_godot", "mod", "deps", "--lockfile_mode=update"), commands)
        (pins,) = [
            command for command in commands if command[1:3] == ("build", "--nobuild")
        ]
        self.assertIn(
            "@@autoload_rules_godot++godot_engines+simulation_macos_arm64_editor//:engine_library",
            pins,
        )

    def test_an_engine_the_root_does_not_use_fails_the_pin_check(self) -> None:
        with (
            mock.patch.object(generate, "repo_mapping", return_value={}),
            mock.patch.object(generate, "bazel", return_value=0),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(1, generate.pins())
        self.assertIn("does not use_repo", stderr.getvalue())

    def test_the_pinned_engines_are_those_declared_with_a_lock_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "MODULE.bazel").write_text(
                'engines = use_extension("@r//godot:extensions.bzl", "godot_engines")\n'
                'engines.engine(name = "godot", version = "4.7.2")\n'
                "engines.engine(\n"
                '    name = "simulation",\n'
                '    lock_file = "//examples/engines/sim:godot_simulation.lock.json",\n'
                ")\n"
            )
            self.assertEqual(
                (
                    (
                        "simulation",
                        root / "examples/engines/sim/godot_simulation.lock.json",
                    ),
                ),
                generate.pinned_engines(root),
            )

    def test_the_pin_check_covers_only_the_pinned_recipes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "simulation.lock.json"
            lock.write_text(
                '{"recipes": {"macos_arm64_editor": {}, "linux_x86_64_editor": {}}}'
            )
            self.assertEqual(
                [
                    "@@ext+simulation_linux_x86_64_editor//:engine_library",
                    "@@ext+simulation_macos_arm64_editor//:engine_library",
                ],
                generate.pinned_payloads(
                    "simulation", lock, {"simulation": "ext+simulation"}
                ),
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
