"""Tests of how a change's files are judged and reported."""

import unittest

from tools.code_health.change import FileChange, directive, report
from tools.code_health.scan import FileResult
from tools.git.changes import ChangedPath


def result(path: str, score: float | None, *smells: tuple[str, str, int]) -> FileResult:
    """A file's result with findings given as (category, function, start line)."""
    return FileResult(
        path,
        "Python",
        10,
        score,
        [
            {
                "category": category,
                "functions": [
                    {
                        "name": f"{function}:{start}",
                        "start": start,
                        "end": start + 9,
                        "details": "cc = 12",
                    }
                ],
            }
            for category, function, start in smells
        ],
    )


class DeclineTest(unittest.TestCase):
    def change(self, before: float | None, after: float | None) -> FileChange:
        return FileChange(
            ChangedPath("a.py" if before is not None else None, "a.py"),
            result("a.py", before) if before is not None else None,
            result("a.py", after),
        )

    def test_a_falling_score_declines(self) -> None:
        self.assertTrue(self.change(9.5, 9.4).declined)
        self.assertFalse(self.change(9.4, 9.4).declined)
        self.assertFalse(self.change(9.4, 9.8).declined)

    def test_a_new_file_declines_below_nine(self) -> None:
        self.assertTrue(self.change(None, 8.99).declined)
        self.assertFalse(self.change(None, 9.0).declined)

    def test_a_file_without_scorable_code_before_counts_as_new(self) -> None:
        change = FileChange(
            ChangedPath("a.py", "a.py"), result("a.py", None), result("a.py", 8.5)
        )
        self.assertTrue(change.declined)

    def test_deleted_files_and_files_without_scorable_code_never_decline(self) -> None:
        deleted = FileChange(ChangedPath("a.py", None), result("a.py", 7.0), None)
        unscored = FileChange(ChangedPath(None, "a.py"), None, result("a.py", None))
        self.assertFalse(deleted.declined)
        self.assertFalse(unscored.declined)


class ReportTest(unittest.TestCase):
    def test_new_findings_name_their_function_and_lines(self) -> None:
        change = FileChange(
            ChangedPath("a.py", "a.py"),
            result("a.py", 9.5, ("Complex Method", "kept", 5)),
            result(
                "a.py",
                9.1,
                ("Complex Method", "kept", 7),
                ("Bumpy Road Ahead", "grown", 30),
            ),
        )
        self.assertEqual(
            [("Bumpy Road Ahead", "grown:30")],
            [(category, f["name"]) for category, f in change.new_findings],
        )
        text = report([change], "`main`", [], all_findings=False)
        self.assertIn("| `a.py` | 9.50 | 9.10 | -0.40 |", text)
        self.assertIn("**declined**", text)
        self.assertIn("- Bumpy Road Ahead (`grown:30`, lines 30-39): cc = 12", text)
        self.assertNotIn("`kept:7`", text)
        self.assertIn('- `# @codescene(disable:"Bumpy Road Ahead")` above `grown`', text)
        self.assertIn("docs/internal/code-health.md", text)

    def test_directives_use_the_comment_of_the_file_s_language(self) -> None:
        self.assertEqual(
            [
                '# @codescene(disable:"Complex Method")',
                '# @codescene(disable:"Complex Method")',
                '# @codescene(disable:"Complex Method")',
                '// @codescene(disable:"Complex Method")',
            ],
            [
                directive(path, "Complex Method")
                for path in ("a/defs.bzl", "a/game.gd", "a/BUILD.bazel", "a/app.cc")
            ],
        )

    def test_files_that_do_not_decline_get_no_directives(self) -> None:
        change = FileChange(
            ChangedPath("a.py", "a.py"),
            result("a.py", 9.0),
            result("a.py", 9.5, ("Complex Method", "grown", 3)),
        )
        text = report([change], "`main`", [], all_findings=False)
        self.assertIn("Complex Method (`grown:3`", text)
        self.assertNotIn("@codescene", text)

    def test_declined_files_come_first(self) -> None:
        better = FileChange(
            ChangedPath("b.py", "b.py"), result("b.py", 8.0), result("b.py", 9.0)
        )
        worse = FileChange(
            ChangedPath("w.py", "w.py"), result("w.py", 9.9), result("w.py", 9.8)
        )
        text = report([better, worse], "`main`", [], all_findings=False)
        self.assertLess(text.index("`w.py`"), text.index("`b.py`"))
        self.assertIn("declined: 1.", text)

    def test_only_lists_the_findings_a_file_had_before_too(self) -> None:
        change = FileChange(
            ChangedPath("a.py", "a.py"),
            result("a.py", 9.5, ("Complex Method", "kept", 5)),
            result("a.py", 9.5, ("Complex Method", "kept", 5)),
        )
        self.assertNotIn("`kept:5`", report([change], "`main`", [], all_findings=False))
        self.assertIn(
            "- Complex Method (`kept:5`, lines 5-14): cc = 12",
            report([change], "`main`", [], all_findings=True),
        )


if __name__ == "__main__":
    unittest.main()
