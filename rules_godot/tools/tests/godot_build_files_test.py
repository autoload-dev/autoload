"""The generated BUILD files of Godot projects: discovery, rendering and check mode."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tools.godot_build_files import discover, main, render, update


class BuildFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def source(self, path: str, contents: str = "") -> Path:
        source = self.root / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(contents, encoding="utf-8")
        return source

    def test_stable_explicit_sources_and_check_mode_leave_build_untouched(self) -> None:
        manual = self.source("BUILD.bazel", "# Manual policy.\n")
        self.source("project.godot")
        self.source("z.tscn")
        self.source("a.gd")
        self.source("a.gd.uid")
        self.source(".godot/imported/hidden.tres")
        self.source("documentation.md")
        output = self.root / "godot_files.bzl"
        self.assertFalse(update(self.root, output, check=True))
        self.assertFalse(output.exists())
        self.assertFalse(update(self.root, output))
        self.assertTrue(update(self.root, output, check=True))
        self.assertEqual(
            render(["a.gd", "a.gd.uid", "z.tscn"]), output.read_text(encoding="utf-8")
        )
        self.assertEqual("# Manual policy.\n", manual.read_text(encoding="utf-8"))
        self.source("new.tres")
        self.assertFalse(update(self.root, output, check=True))
        self.assertNotIn('"new.tres"', output.read_text(encoding="utf-8"))
        update(self.root, output)
        (self.root / "a.gd").unlink()
        (self.root / "a.gd.uid").unlink()
        self.assertFalse(update(self.root, output, check=True))
        update(self.root, output)
        self.assertEqual(
            render(["new.tres", "z.tscn"]), output.read_text(encoding="utf-8")
        )

    def test_refuses_manual_or_symlink_outputs(self) -> None:
        output = self.source("manual.bzl", "# Authored\n")
        with self.assertRaisesRegex(ValueError, "unmarked"):
            update(self.root, output)
        link = self.root / "linked.bzl"
        link.symlink_to(output)
        with self.assertRaisesRegex(ValueError, "symlink"):
            update(self.root, link)
        with self.assertRaisesRegex(ValueError, "dedicated .bzl"):
            update(self.root, self.root / "BUILD.bazel")

    def test_nested_package_and_symlink_boundaries(self) -> None:
        self.source("root.gd")
        self.source("nested/BUILD.bazel")
        self.source("nested/child.gd")
        self.source("nested/deeper/other.gd")
        self.source("ordinary/child.gd")
        (self.root / "linked.gd").symlink_to(self.root / "root.gd")
        (self.root / "linked_dir").symlink_to(
            self.root / "ordinary", target_is_directory=True
        )
        self.assertEqual(["ordinary/child.gd", "root.gd"], discover(self.root))

    def test_directories_godot_ignores_hold_no_resources(self) -> None:
        self.source("root.gd")
        self.source("report/.gdignore")
        self.source("report/helper.gd")
        self.source("demo/project.godot")
        self.source("demo/demo.gd")
        self.assertEqual(["root.gd"], discover(self.root))

    def test_a_package_directory_godot_ignores_holds_no_resources(self) -> None:
        self.source(".gdignore")
        self.source("template.gd")
        self.assertEqual([], discover(self.root))
        # A project's root directory, which Godot always scans.
        self.source("project.godot")
        self.assertEqual(["template.gd"], discover(self.root))

    def test_sidecars_follow_their_collected_file(self) -> None:
        self.source("a.gd")
        self.source("a.gd.uid")
        self.source("clip.ogv")
        self.source("clip.ogv.import")
        self.source("stray.uid")
        self.source("stray.UID")
        self.source("a.gd.uid.uid")
        self.assertEqual(["a.gd", "a.gd.uid"], discover(self.root))
        self.assertEqual(
            ["clip.ogv", "clip.ogv.import"], discover(self.root, includes=["*.ogv"])
        )

    def test_include_and_exclude_keep_custom_loaders_explicit(self) -> None:
        self.source("data/custom.bin")
        self.source("data/not-chosen.bin")
        self.source("script.gd")
        self.assertEqual(
            ["data/custom.bin"],
            discover(self.root, includes=["data/*.bin"], excludes=["*not-chosen*"]),
        )

    def test_broad_include_pattern_keeps_generation_idempotent(self) -> None:
        self.source("asset.custom", "value")
        output = self.root / "godot_files.bzl"
        self.assertFalse(update(self.root, output, includes=["*"]))
        self.assertTrue(update(self.root, output, includes=["*"], check=True))
        self.assertEqual(render(["asset.custom"]), output.read_text(encoding="utf-8"))

    def test_cli_check_reports_drift_and_preserves_existing_result(self) -> None:
        self.source("main.gd")
        self.assertEqual(0, main(["--root", str(self.root)]))
        self.assertEqual(0, main(["--root", str(self.root), "--check"]))
        self.source("added.tres")
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(1, main(["--root", str(self.root), "--check"]))
        self.assertIn("stale", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
