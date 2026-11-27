"""Regressions for the per-file rules on given files: their paths and their findings."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from tools.conventions.files import main, repository_path
from tools.conventions.per_file import RULES
from tools.conventions.registry import select
from tools.setup.modules import module_directory


class FilesTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)

    def write(self, path: str, text: str) -> str:
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text)
        return path

    def check(self, *arguments: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            return main(list(arguments)), output.getvalue()

    def test_names_files_by_their_path_in_the_repository(self) -> None:
        self.assertEqual("a/b.py", repository_path("a/b.py", ""))
        self.assertEqual("rules_godot/a/b.py", repository_path("a/b.py", "rules_godot"))
        self.assertEqual(
            "addons/sqlite/a/b.md",
            repository_path("external/autoload_sqlite+/a/b.md", "rules_godot"),
        )
        self.assertEqual(Path("."), module_directory("autoload_dev"))
        self.assertEqual(Path("rules_godot"), module_directory("autoload_rules_godot"))

    def test_reports_a_finding_at_the_file_s_repository_path(self) -> None:
        script = self.write("tools/a.py", "# ---- Section ----\nx = 1\n")
        module = self.write("MODULE.bazel", 'module(name = "autoload_rules_godot")\n')
        code, output = self.check(
            "--module-file", module, "--rule", "region-headers", script
        )
        self.assertEqual(1, code)
        self.assertIn("rules_godot/tools/a.py:1: region-headers", output)

    def test_judges_documents_by_their_place(self) -> None:
        guide = self.write("docs/public/guide.md", "See [internals](../internal/a.md).\n")
        internal = self.write("docs/internal/a.md", "See [more](b.md).\n")
        module = self.write(
            "MODULE.bazel", 'module(\n    name = "autoload_rules_godot",\n)\n'
        )
        code, output = self.check(
            "--module-file",
            module,
            "--rule",
            "public-documentation-links",
            guide,
            internal,
        )
        self.assertEqual(1, code)
        self.assertIn(
            "rules_godot/docs/public/guide.md:1: public-documentation-links", output
        )
        self.assertNotIn("docs/internal/a.md:1", output)

    def test_passes_clean_files_and_refuses_rules_that_need_more(self) -> None:
        clean = self.write("a.py", "x = 1\n")
        self.assertEqual(
            (0, ""),
            self.check("--rule", "region-headers", "--rule", "reading-order", clean),
        )
        self.assertEqual(2, self.check("--rule", "RG001", clean)[0])

    def test_the_tool_leaves_out_per_file_rules_unless_named(self) -> None:
        per_file = {rule.info.id for rule in RULES}
        self.assertEqual(
            {
                "fixture-references",
                "public-documentation-links",
                "region-headers",
                "reading-order",
            },
            per_file,
        )
        self.assertFalse(per_file & {rule.info.id for rule in select()})
        self.assertEqual(
            ["region-headers"], [rule.info.id for rule in select(["region-headers"])]
        )


if __name__ == "__main__":
    unittest.main()
