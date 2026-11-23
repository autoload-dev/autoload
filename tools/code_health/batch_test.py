"""Tests of reviewing many files in one CLI run, and of the result cache."""

import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tools.code_health.batch import Reviewer, batches, cli_identity
from tools.code_health.translation import Translation

# A stand-in for `cs review --file-list .files.txt --output-format jsonl`: it scores each listed
# file by its line count, reports the rules it saw, counts its runs and fails on "fail.py".
FAKE_CLI = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, pathlib, sys
    runs = pathlib.Path(__file__).with_name("runs")
    runs.write_text(str(int(runs.read_text()) + 1) if runs.exists() else "1")
    rules = pathlib.Path(".codescene/code-health-rules.json")
    for name in pathlib.Path(".files.txt").read_text().split():
        print("a notice that is not JSON")
        if name.endswith("fail.py"):
            print("license check failed", file=sys.stderr)
            continue
        lines = len(pathlib.Path(name).read_text().splitlines())
        row = {"path": name, "score": float(lines), "review": [],
               "rules": rules.read_text() if rules.exists() else None,
               "git_dir": os.environ.get("GIT_DIR")}
        print(json.dumps(row))
    """)


class ReviewerTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.cli = self.root / "cs"
        self.cli.write_text(FAKE_CLI)
        self.cli.chmod(self.cli.stat().st_mode | stat.S_IEXEC)

    def reviewer(
        self, rules: str | None = None, identity: str | None = "1.0"
    ) -> Reviewer:
        return Reviewer(str(self.cli), {}, identity, rules, self.root / "cache")

    def scores(self, *translations: Translation, **options: str | None) -> list[object]:
        return [
            result.get("score")
            for result in self.reviewer(**options).review([*translations])
        ]

    def runs(self) -> int:
        runs = self.root / "runs"
        return int(runs.read_text()) if runs.exists() else 0

    def test_all_files_are_reviewed_in_one_run_at_their_own_paths(self) -> None:
        scores = self.scores(
            Translation("tools/a.py", "x = 1\n"),
            Translation("b.bzl.py", "x = 1\ny = 2\n"),
        )
        self.assertEqual([1.0, 2.0], scores)
        self.assertEqual(1, self.runs())

    def test_two_revisions_of_one_path_are_reviewed_in_separate_runs(self) -> None:
        scores = self.scores(
            Translation("a.py", "x = 1\n"), Translation("a.py", "x = 1\ny = 2\n")
        )
        self.assertEqual([1.0, 2.0], scores)
        self.assertEqual(2, self.runs())

    def test_an_unchanged_file_comes_from_the_cache(self) -> None:
        self.scores(Translation("a.py", "x = 1\n"))
        self.assertEqual([1.0], self.scores(Translation("a.py", "x = 1\n")))
        self.assertEqual(1, self.runs())

    def test_another_cli_or_other_rules_review_again(self) -> None:
        self.scores(Translation("a.py", "x = 1\n"))
        self.scores(Translation("a.py", "x = 1\n"), identity="2.0")
        results = self.reviewer(rules="{}").review([Translation("a.py", "x = 1\n")])
        self.assertEqual(3, self.runs())
        self.assertEqual("{}", results[0]["rules"])

    def test_without_an_identity_nothing_is_cached(self) -> None:
        self.scores(Translation("a.py", "x = 1\n"), identity=None)
        self.scores(Translation("a.py", "x = 1\n"), identity=None)
        self.assertEqual(2, self.runs())

    def test_a_file_the_cli_did_not_review_gets_its_error_and_is_not_cached(self) -> None:
        files = [Translation("a.py", "x = 1\n"), Translation("fail.py", "x = 1\n")]
        results = self.reviewer().review(files)
        self.assertEqual({"error": "license check failed"}, results[1])
        self.reviewer().review(files)
        self.assertEqual(2, self.runs())

    def test_a_git_hooks_repository_is_left_alone(self) -> None:
        repository = self.root / "repository"
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        hook = {"GIT_DIR": str(repository / ".git"), "GIT_WORK_TREE": str(repository)}
        with mock.patch.dict(os.environ, hook):
            reviewer = Reviewer(str(self.cli), hook, "1.0", None, self.root / "cache")
            results = reviewer.review([Translation("a.py", "x = 1\n")])
        self.assertEqual(1.0, results[0]["score"])
        self.assertIsNone(results[0]["git_dir"])
        worktree = subprocess.run(
            [
                "git",
                "config",
                "--file",
                str(repository / ".git" / "config"),
                "core.worktree",
            ],
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, worktree.returncode, "core.worktree was written")

    def test_a_binary_named_cs_is_identified_without_running_it(self) -> None:
        identity = cli_identity(str(self.cli), {})
        self.assertIsNotNone(identity)
        self.assertIn(str(self.cli.resolve()), identity or "")
        self.assertEqual(0, self.runs())


class BatchesTest(unittest.TestCase):
    def test_no_path_occurs_twice_in_a_batch(self) -> None:
        split = batches(
            {
                "1": Translation("a.py", "1"),
                "2": Translation("b.py", "2"),
                "3": Translation("a.py", "3"),
            }
        )
        self.assertEqual([["1", "2"], ["3"]], [list(batch) for batch in split])


if __name__ == "__main__":
    unittest.main()
