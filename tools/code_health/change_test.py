"""Tests of how a change's files are found, judged and reported."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.code_health.change import (
    ChangedPath,
    FileChange,
    changed_paths,
    directive,
    merge_base,
    parse_name_status,
    report,
    staged_paths,
)
from tools.code_health.scan import FileResult

# A Git that reads no user or system configuration, such as signing or hooks.
GIT_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


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


class NameStatusTest(unittest.TestCase):
    def test_each_status_names_the_file_on_each_side(self) -> None:
        output = "M\0kept.py\0A\0new.py\0D\0gone.py\0R087\0old.py\0moved.py\0"
        self.assertEqual(
            [
                ChangedPath("kept.py", "kept.py"),
                ChangedPath(None, "new.py"),
                ChangedPath("gone.py", None),
                ChangedPath("old.py", "moved.py"),
            ],
            parse_name_status(output),
        )

    def test_a_rename_is_labelled_with_both_paths(self) -> None:
        self.assertEqual("old.py → moved.py", ChangedPath("old.py", "moved.py").label)
        self.assertEqual("kept.py", ChangedPath("kept.py", "kept.py").label)


class ChangedPathsTest(unittest.TestCase):
    def setUp(self) -> None:
        environment = mock.patch.dict(os.environ, GIT_ENVIRONMENT)
        environment.start()
        self.addCleanup(environment.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name)
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.repo), *args], check=True)

    def commit(self, files: dict[str, str], message: str) -> None:
        for path, text in files.items():
            (self.repo / path).write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def test_the_change_is_the_working_tree_against_the_merge_base(self) -> None:
        body = "".join(f"line {n}\n" for n in range(20))
        self.commit({"stays.py": "x = 1\n", "moves.py": body}, "base")
        self.git("switch", "-q", "-c", "feature")
        self.git("mv", "moves.py", "moved.py")
        self.commit({"stays.py": "x = 2\n"}, "feature")
        self.git("switch", "-q", "main")
        self.commit({"later.py": "z = 1\n"}, "lands on main after the branch point")
        self.git("switch", "-q", "feature")
        (self.repo / "untracked.py").write_text("y = 1\n")

        since = merge_base(self.repo, "main")
        self.assertCountEqual(
            [
                ChangedPath("moves.py", "moved.py"),
                ChangedPath("stays.py", "stays.py"),
                ChangedPath(None, "untracked.py"),
            ],
            changed_paths(self.repo, since),
        )

    def test_staged_changes_are_the_index_against_head(self) -> None:
        body = "".join(f"line {n}\n" for n in range(20))
        self.commit({"stays.py": "x = 1\n", "moves.py": body}, "base")
        self.git("mv", "moves.py", "moved.py")
        (self.repo / "stays.py").write_text("x = 2\n")
        self.git("add", "stays.py")
        (self.repo / "unstaged.py").write_text("y = 1\n")

        self.assertCountEqual(
            [ChangedPath("moves.py", "moved.py"), ChangedPath("stays.py", "stays.py")],
            staged_paths(self.repo),
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
