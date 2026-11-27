"""Tests of how the files of a change are found."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.git.changes import (
    ChangedPath,
    GitError,
    changed_paths,
    git,
    merge_base,
    parse_name_status,
    staged_paths,
)

# A Git that reads no user or system configuration, such as signing or hooks.
GIT_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


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
        assert since is not None
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

    def test_the_first_commit_stages_against_nothing(self) -> None:
        (self.repo / "first.py").write_text("x = 1\n")
        self.git("add", "first.py")

        self.assertEqual([ChangedPath(None, "first.py")], staged_paths(self.repo))

    def test_a_failing_git_reports_what_git_printed(self) -> None:
        with self.assertRaisesRegex(GitError, "no-such-ref"):
            git(self.repo, "rev-parse", "--verify", "no-such-ref^{commit}")

    def test_unrelated_histories_have_no_merge_base(self) -> None:
        self.commit({"a.py": "x = 1\n"}, "base")
        self.git("switch", "-q", "--orphan", "other")
        self.commit({"b.py": "y = 1\n"}, "unrelated")

        self.assertIsNone(merge_base(self.repo, "main"))


if __name__ == "__main__":
    unittest.main()
