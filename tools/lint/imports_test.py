"""The file lint's import-linter run (imports.py) over a module of its own."""

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.lint.imports import main

CONTRACTS = """
[importlinter]
root_package = layered

[importlinter:contract:layers]
name = Top is above bottom
type = layers
layers =
    layered.top
    layered.bottom

[importlinter:contract:forbidden]
name = Tools do not import top
type = forbidden
source_modules =
    layered.tool
forbidden_modules =
    layered.top
"""


class ImportsTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.module = self.root / "module"
        (self.module / "layered").mkdir(parents=True)
        (self.module / "MODULE.bazel").write_text("")
        (self.module / "layers.ini").write_text(CONTRACTS)
        (self.root / "elsewhere.py").write_text("")
        self.source("top", "from layered import bottom\n")
        self.source("bottom", "")
        self.source("tool", "from layered import bottom\n")

    def source(self, name: str, text: str) -> None:
        (self.module / "layered" / f"{name}.py").write_text(textwrap.dedent(text))

    def lint(self, *files: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.chdir(self.root), contextlib.redirect_stdout(output):
            code = main(list(files) or ["module/layered/top.py", "elsewhere.py"])
        return code, output.getvalue()

    def test_kept_contracts_print_nothing(self) -> None:
        self.assertEqual((0, ""), self.lint())

    def test_each_broken_chain_names_the_import_that_breaks_it(self) -> None:
        self.source("bottom", "\n\nfrom layered import top\n")
        self.source("tool", "from layered import bottom\n")
        code, output = self.lint()
        self.assertEqual(1, code)
        self.assertIn(
            "module/layered/bottom.py:3: imports layered.top, "
            "which the contract 'Top is above bottom' forbids",
            output.splitlines(),
        )
        self.assertIn(
            "module/layered/bottom.py:3: imports layered.top, "
            "which the contract 'Tools do not import top' forbids",
            output.splitlines(),
        )

    def test_a_changed_contracts_file_is_checked_on_its_own(self) -> None:
        self.source("bottom", "from layered import top\n")
        code, output = self.lint("module/layers.ini")
        self.assertEqual(1, code)
        self.assertIn("module/layered/bottom.py:1: imports layered.top", output)

    def test_a_module_it_cannot_parse_leaves_the_contracts_unchecked(self) -> None:
        self.source("bottom", "def broken(:\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, self.lint()[0])


if __name__ == "__main__":
    unittest.main()
