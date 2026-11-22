"""Open an editor view headless on a copy of a fixture's checkout and check what reached it."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.godot_staging import copy_file

# Godot's terminal colors and cursor movements.
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

_PACKAGE = "godot/private/tests/editor_view/fixtures/project_edited_in_the_view"


class GodotEditorTest(unittest.TestCase):
    """One editor session; each test checks one of its results."""

    @classmethod
    def setUpClass(cls) -> None:
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR"))
        cls.addClassCleanup(temporary.cleanup)
        base = Path(temporary.name)
        runfiles = Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"]
        cls.workspace = base / "workspace"
        # The view links into this copy, so the test never edits the source tree.
        # Only the fixture's checkout files are copied; the package's runfiles also
        # hold build outputs.
        for path in os.environ["CHECKOUT"].split():
            copy_file(runfiles / path, cls.workspace / path)
        (cls.workspace / ".bazelignore").write_text(".godot-editor\n")
        environment = dict(os.environ, BUILD_WORKSPACE_DIRECTORY=str(cls.workspace))
        for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            environment[name] = str(base / name.lower())

        def run(variable: str, *args: str) -> tuple[int, str]:
            result = subprocess.run(
                [str(runfiles / os.environ[variable]), *args],
                check=False,
                env=environment,
                capture_output=True,
                text=True,
                timeout=240,
            )
            return result.returncode, _ANSI.sub("", result.stdout + result.stderr)

        cls.package = cls.workspace / _PACKAGE
        # The fixture declares no sidecars; the check runs before the view opens.
        cls.check = run("METADATA_TEST")
        cls.icon_sidecar_before = (cls.package / "main/levels/icon.svg.import").exists()
        cls.edit = run("EDIT", "--headless")
        cls.sync = run("METADATA")

    def test_metadata_check_names_missing_sidecars(self) -> None:
        code, output = self.check
        self.assertEqual(code, 1, output)
        self.assertIn(
            f"{_PACKAGE}/main/levels/icon.svg.import is missing or not declared; write "
            f"it with bazel run //{_PACKAGE}:metadata",
            output,
        )
        self.assertFalse(self.icon_sidecar_before)

    def test_sidecars_are_written_before_the_view_opens(self) -> None:
        code, output = self.edit
        self.assertEqual(code, 0, output)
        self.assertIn(f"wrote {_PACKAGE}/main/levels/icon.svg.import", output)
        # An imported asset keeps its UID in its .import file.
        for sidecar in ("main/main.gd.uid", "main/levels/icon.svg.import"):
            self.assertTrue((self.package / sidecar).is_file(), sidecar)
        self.assertFalse((self.package / "main/levels/icon.svg.uid").exists())

    def test_enabled_plugin_runs_with_the_extension_loaded(self) -> None:
        _, output = self.edit
        self.assertIn("VIEW_CHECK done", output)
        self.assertIn("VIEW_CHECK extension_loaded=true", output)
        self.assertIn("VIEW_CHECK icon_imported=true", output)

    def test_view_opens_on_the_build_imports_without_reimport(self) -> None:
        _, output = self.edit
        self.assertNotIn("(Re)Importing", output)

    def test_plugin_enabled_only_in_the_authored_project_file_stays_off(self) -> None:
        _, output = self.edit
        self.assertNotIn("authored_only_ran", output)

    def test_edits_write_back_to_the_checkout(self) -> None:
        self.assertEqual((self.package / "main/main.gd").read_text(), "extends Node2D\n")
        self.assertEqual(
            (self.package / "main/levels/two.json").read_text(), '{"level": 2}\n'
        )

    def test_files_only_in_the_view_stay_there(self) -> None:
        _, output = self.edit
        self.assertFalse((self.package / "notes.gd").exists())
        view = self.workspace / ".godot-editor" / _PACKAGE / "edit"
        self.assertTrue((view / "notes.gd").is_file())
        self.assertIn("res://notes.gd exists only in the view", output)
        self.assertNotIn("wrote ;", output)

    def test_project_file_writeback_excludes_contributed_settings(self) -> None:
        _, output = self.edit
        authored = (self.package / "project.godot").read_text()
        self.assertIn('config/description="Edited in the view"', authored)
        self.assertNotIn("rules_godot/editor", authored)
        self.assertIn(
            f"rules_godot/editor/contributed is set by //{_PACKAGE}:project", output
        )

    def test_metadata_run_reports_undeclared_sidecars(self) -> None:
        code, output = self.sync
        self.assertEqual(code, 0, output)
        self.assertIn(f"{_PACKAGE}/main/main.gd.uid is not declared", output)


if __name__ == "__main__":
    unittest.main()
