"""
The GDScript lint: the rules the repository's .gdlintrc keeps, and the scripts it reads.
The test's argument is the .gdlintrc.
"""

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.lint import gdscript

GDLINTRC = Path(sys.argv.pop(1)).resolve()


class GdscriptTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        shutil.copy(GDLINTRC, self.root / ".gdlintrc")
        subprocess.run(["git", "init", "-q", self.root], check=True)

    def lint(self, *paths: str) -> tuple[int, str]:
        """gdlint's exit code and output over the given scripts, or the tracked ones."""
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
            mock.patch.object(sys, "argv"),
        ):
            try:
                gdscript.main(self.root, list(paths))
            except SystemExit as exit:
                return int(exit.code or 0), output.getvalue()
        return 0, output.getvalue()

    def write(self, path: str, code: str) -> None:
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(code)

    def test_reports_a_definition_out_of_godots_order(self) -> None:
        self.write(
            "a.gd", "extends Node\n\n@onready var label = $Label\nvar count := 0\n"
        )
        code, output = self.lint(str(self.root / "a.gd"))
        self.assertEqual(1, code)
        self.assertIn("a.gd:4: Error: Definition out of order", output)

    def test_lints_every_tracked_script_without_paths(self) -> None:
        self.write(
            "a.gd", "extends Node\n\n@onready var label = $Label\nvar count := 0\n"
        )
        self.write("gone.gd", "extends Node\n")
        subprocess.run(["git", "-C", self.root, "add", "a.gd", "gone.gd"], check=True)
        (self.root / "gone.gd").unlink()
        code, output = self.lint()
        self.assertEqual(1, code)
        self.assertIn("a.gd:4: Error: Definition out of order", output)

    def test_reports_no_other_rule(self) -> None:
        long_line = "var text := '" + "x" * 120 + "'"
        self.write(
            "a.gd", f"extends Node\n\n{long_line}\n\n\nfunc f():\n\tvar BadName := 1\n"
        )
        self.assertEqual(0, self.lint(str(self.root / "a.gd"))[0])

    def test_reads_the_tracked_scripts_but_the_excluded(self) -> None:
        for path in ("a.gd", "b/c.gd", "untracked.gd", "d.md", *gdscript.EXCLUDED):
            self.write(path, "extends Node\n")
        tracked = ["a.gd", "b/c.gd", "d.md", *gdscript.EXCLUDED]
        subprocess.run(["git", "-C", self.root, "add", *tracked], check=True)
        self.assertEqual(["a.gd", "b/c.gd"], gdscript.scripts(self.root))


if __name__ == "__main__":
    unittest.main()
