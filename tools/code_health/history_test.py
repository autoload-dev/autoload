import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.code_health.history import History, history, report, touched

GIT_ENVIRONMENT = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def header(name: str) -> str:
    start = f"# ==== {name} "
    return start + "=" * (80 - len(start))


def module(lexer: str, graph: str) -> str:
    return f'''"""Sections: Lexer, Graph."""

{header("Lexer")}

LEXER = {lexer}
TOKENS = 1

{header("Graph")}

GRAPH = {graph}
EDGES = 2
'''


class HistoryTest(unittest.TestCase):
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

    def commit(self, files: dict[str, str]) -> None:
        for path, text in files.items():
            (self.repo / path).write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")

    def test_commits_partners_and_regions(self) -> None:
        self.commit({"a.py": module("1", "1"), "b.py": "B = 1\n"})
        self.commit({"a.py": module("2", "1"), "b.py": "B = 2\n"})
        self.commit({"a.py": module("3", "2"), "c.py": "C = 1\n"})
        self.commit({"b.py": "B = 3\n"})
        found = history(self.repo, "a.py", None, touched(self.repo, None))
        self.assertEqual(3, found.commits)
        self.assertEqual([("b.py", 2), ("c.py", 1)], found.partners)
        self.assertEqual([(["Graph", "Lexer"], 2), (["Lexer"], 1)], found.together)

    def test_a_renamed_file_keeps_its_history(self) -> None:
        self.commit({"a.py": module("1", "1")})
        self.git("mv", "a.py", "moved.py")
        self.commit({"moved.py": module("2", "1")})
        found = history(self.repo, "moved.py", None, touched(self.repo, None))
        self.assertEqual(2, found.commits)
        self.assertEqual([], found.partners)
        self.assertCountEqual([(["Graph", "Lexer"], 1), (["Lexer"], 1)], found.together)

    def test_the_report_lists_the_most_changed_file_first(self) -> None:
        histories = [
            History("rare.py", 1),
            History("hot.py", 5, [("b.py", 3)], [(["Lexer"], 5)]),
        ]
        text = report(histories, "6.months")
        self.assertLess(text.index("`hot.py`: 5 commits"), text.index("`rare.py`"))
        self.assertIn("Changed most often with: `b.py` (3).", text)
        self.assertIn("| Lexer | 5 |", text)


if __name__ == "__main__":
    unittest.main()
