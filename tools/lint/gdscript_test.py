"""
The GDScript lint: the rules the repository's .gdlintrc keeps and the excluded scripts. The
test's argument is the .gdlintrc.
"""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from tools.lint import gdscript

GDLINTRC = Path(sys.argv.pop(1)).resolve()
OUT_OF_ORDER = "extends Node\n\n@onready var label = $Label\nvar count := 0\n"


class GdscriptTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def lint(self, *paths: str) -> tuple[int, str]:
        """The lint's exit code and output over the given scripts."""
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = gdscript.main(str(GDLINTRC), *paths)
        return code, output.getvalue()

    def write(self, path: str, code: str) -> str:
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(code)
        return str(self.root / path)

    def test_reports_a_definition_out_of_godots_order(self) -> None:
        script = self.write("a.gd", OUT_OF_ORDER)
        code, output = self.lint(script)
        self.assertEqual(1, code)
        self.assertIn(f"{script}:4: Error: Definition out of order", output)

    def test_reports_no_other_rule(self) -> None:
        long_line = "var text := '" + "x" * 120 + "'"
        script = self.write(
            "a.gd", f"extends Node\n\n{long_line}\n\n\nfunc f():\n\tvar BadName := 1\n"
        )
        self.assertEqual((0, "\n"), self.lint(script))

    def test_reports_a_script_that_does_not_parse(self) -> None:
        code, output = self.lint(self.write("a.gd", "extends Node\nfunc (\n"))
        self.assertEqual(1, code)
        self.assertIn("does not parse", output)

    def test_caches_its_grammar_in_a_temporary_directory(self) -> None:
        # Bazel's sandbox mounts the home directory read-only on Linux.
        self.lint(self.write("a.gd", "extends Node\n"))
        cache = Path(gdscript.parser._cache_dirpath).resolve()
        self.assertTrue(cache.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertFalse(cache.is_relative_to(Path.home().resolve()))

    def test_leaves_out_the_excluded_scripts(self) -> None:
        self.assertEqual(0, self.lint(self.write(gdscript.EXCLUDED[0], OUT_OF_ORDER))[0])


if __name__ == "__main__":
    unittest.main()
