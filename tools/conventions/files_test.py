"""Regressions for the per-file rules on given files, named by their paths in the repository."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from tools.conventions.files import main
from tools.conventions.per_file import RULES
from tools.conventions.registry import select


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

    def test_reports_a_finding_at_the_file_s_repository_path(self) -> None:
        script = self.write("rules_godot/tools/a.py", "# ---- Section ----\nx = 1\n")
        code, output = self.check("--rule", "region-headers-named-in-head", script)
        self.assertEqual(1, code)
        self.assertIn("rules_godot/tools/a.py:1: region-headers-named-in-head", output)

    def test_judges_documents_by_their_place(self) -> None:
        guide = self.write(
            "rules_godot/docs/public/guide.md", "See [internals](../internal/a.md).\n"
        )
        internal = self.write("rules_godot/docs/internal/a.md", "See [more](b.md).\n")
        code, output = self.check(
            "--rule", "no-internal-links-in-public-documentation", guide, internal
        )
        self.assertEqual(1, code)
        self.assertIn(
            "rules_godot/docs/public/guide.md:1: no-internal-links-in-public-documentation",
            output,
        )
        self.assertNotIn("docs/internal/a.md:1", output)

    def test_passes_clean_files_and_refuses_rules_that_need_more(self) -> None:
        clean = self.write("a.py", "x = 1\n")
        self.assertEqual(
            (0, ""),
            self.check(
                "--rule",
                "region-headers-named-in-head",
                "--rule",
                "definitions-before-callers",
                clean,
            ),
        )
        self.assertEqual(
            2, self.check("--rule", "project-named-after-directory", clean)[0]
        )

    def test_the_tool_leaves_out_per_file_rules_unless_named(self) -> None:
        per_file = {rule.info.name for rule in RULES}
        self.assertEqual(
            {
                "snake-case-package-paths",
                "no-claude-md",
                "no-end-to-end-tests-in-public-documentation",
                "no-internal-links-in-public-documentation",
                "region-headers-named-in-head",
                "definitions-before-callers",
                "shared-module-files-as-generated",
            },
            per_file,
        )
        self.assertFalse(per_file & {rule.info.name for rule in select()})
        self.assertEqual(
            ["region-headers-named-in-head"],
            [rule.info.name for rule in select(["region-headers-named-in-head"])],
        )


if __name__ == "__main__":
    unittest.main()
