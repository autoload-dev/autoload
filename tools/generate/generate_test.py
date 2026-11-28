"""Tests of what the generators regenerate for a change."""

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
        with (
            mock.patch.object(generate, "bazel", return_value=0) as bazel,
            mock.patch.object(generate.declarations, "write"),
            mock.patch.object(generate.new, "stale_shared_files", return_value={}),
            mock.patch.object(generate, "stale_ruleset_license", return_value={}),
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

    def shared(
        self, paths: list[str], stale: dict[Path, str], unstaged: list[str]
    ) -> tuple[int, list[dict[Path, str]]]:
        """Regenerate for the paths: its status and the files written, by path."""
        with (
            mock.patch.object(generate, "bazel", return_value=0),
            mock.patch.object(generate.declarations, "write") as write,
            mock.patch.object(generate.new, "stale_shared_files", return_value=stale),
            mock.patch.object(generate, "stale_ruleset_license", return_value={}),
            mock.patch.object(generate.new, "write_files") as written,
            mock.patch.object(generate, "unstaged_files", return_value=unstaged),
        ):
            status = generate.regenerate(paths)
        write.assert_called_once_with(generate.ROOT)
        return status, [c.args[1] for c in written.call_args_list]

    def test_the_add_on_declarations_and_stale_shared_files_are_written(self) -> None:
        stale = {Path("addons/x/.bazelrc"): "import\n"}
        self.assertEqual(
            (0, [stale]), self.shared(["tools/addons/template/x.tmpl"], stale, [])
        )

    def test_a_shared_file_with_edits_is_not_overwritten(self) -> None:
        stale = {Path("addons/x/.bazelrc"): "import\n"}
        for staged, unstaged in (
            (["addons/x/.bazelrc"], []),
            (["a.md"], ["addons/x/.bazelrc"]),
        ):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual((1, []), self.shared(staged, stale, unstaged))
            self.assertIn("addons/x/.bazelrc", output.getvalue())

    def test_without_paths_every_stale_shared_file_is_written(self) -> None:
        stale = {Path("addons/x/.bazelrc"): "import\n"}
        self.assertEqual((0, [stale]), self.shared([], stale, ["addons/x/.bazelrc"]))

    def test_the_ruleset_carries_the_repository_license(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "LICENSE").write_text("license\n")
            (root / "rules_godot").mkdir()
            stale = generate.stale_ruleset_license(root)
            self.assertEqual({Path("rules_godot/LICENSE"): "license\n"}, stale)
            generate.new.write_files(root, stale)
            self.assertEqual({}, generate.stale_ruleset_license(root))


if __name__ == "__main__":
    unittest.main()
