"""
The file lint (files.py): which files each tool gets in each scope, and how the tools'
exit codes and findings decide the run.
"""

import contextlib
import io
import subprocess
import tempfile
import textwrap
import unittest
from dataclasses import replace
from pathlib import Path

from tools.lint.files import (
    TOOLS,
    Tool,
    changed_files,
    listed_files,
    run,
)

# A tool's script that records its arguments beside itself.
RECORDING = 'echo "$@" >> "$0.log"\n'

GIT = ("git", "-c", "user.name=Test", "-c", "user.email=test@example.com")


class FilesTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "repository"
        self.bin = Path(directory.name) / "bin"
        self.root.mkdir()
        self.bin.mkdir()

    def git(self, *arguments: str) -> None:
        subprocess.run([*GIT, *arguments], cwd=self.root, check=True, capture_output=True)

    def write(self, path: str, text: str = "x\n") -> str:
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text)
        return path

    def tool(
        self,
        name: str,
        script: str = RECORDING,
        check: tuple[str, ...] | None = None,
        fix: tuple[str, ...] | None = None,
    ) -> Tool:
        """A tool of Markdown whose executable is a shell script, which may record its arguments."""
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + textwrap.dedent(script))
        path.chmod(0o755)
        return Tool(name, ("*.md",), check=check, fix=fix)

    def recorded(self, name: str) -> list[str]:
        log = self.bin / (name + ".log")
        return log.read_text().split() if log.exists() else []

    def lint(
        self, tools: tuple[Tool, ...], files: list[str], fix: bool = False
    ) -> tuple[int, str]:
        executables = {tool: str(self.bin / tool.name) for tool in tools}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run(executables, files, self.root, fix=fix)
        return code, output.getvalue()

    def test_every_file_git_lists_but_ignored_ones(self) -> None:
        self.write(".gitignore", "ignored.md\n")
        self.write("kept.md")
        self.write("gone.md")
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        (self.root / "gone.md").unlink()
        self.write("ignored.md")
        self.write("new/untracked.md")
        self.assertEqual(
            [".gitignore", "gone.md", "kept.md", "new/untracked.md"],
            listed_files(self.root),
        )

    def test_changed_files_since_the_merge_base_with_the_working_tree(self) -> None:
        self.write("same.md")
        self.write("edited.md")
        self.write("removed.md")
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        self.git("checkout", "-q", "-b", "change")
        self.write("committed.md")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "change")
        self.write("edited.md", "y\n")
        (self.root / "removed.md").unlink()
        self.write("untracked.md")
        self.assertEqual(
            ["committed.md", "edited.md", "untracked.md"],
            changed_files(self.root, "main"),
        )

    def test_a_tool_takes_its_files_by_name_suffix_or_shell_shebang(self) -> None:
        shell = Tool("shell", ("*.sh",), check=(), shebang=True)
        self.write("tools/bazel", "#!/usr/bin/env bash\n")
        self.write("tools/data", "plain\n")
        self.write("tools/run.sh")
        self.write("tools/run.py", "#!/usr/bin/env bash\n")
        files = ["tools/bazel", "tools/data", "tools/run.sh", "tools/run.py"]
        self.assertEqual(
            ["tools/bazel", "tools/run.sh"], shell.selected(files, self.root)
        )
        named = Tool("named", ("BUILD.bazel", "*.bzl"), check=(), excluded=("x/*",))
        self.assertEqual(
            ["a/BUILD.bazel", "b.bzl"],
            named.selected(["a/BUILD.bazel", "b.bzl", "x/c.bzl", "BUILD.txt"], self.root),
        )

    def test_runs_each_tool_once_on_its_files_and_passes_when_all_pass(self) -> None:
        tools = (
            self.tool("md", check=("check",)),
            replace(self.tool("gd", check=()), patterns=("*.gd",)),
            replace(self.tool("py", check=()), patterns=("*.py",)),
        )
        self.write("a.md")
        self.write("b/c.md")
        self.write("d.gd")
        self.assertEqual((0, ""), self.lint(tools, ["a.md", "b/c.md", "d.gd"]))
        self.assertEqual(["check", "a.md", "b/c.md"], self.recorded("md"))
        self.assertEqual(["d.gd"], self.recorded("gd"))
        self.assertEqual([], self.recorded("py"))

    def test_fails_with_the_findings_of_each_tool_that_found_some(self) -> None:
        tools = (
            self.tool("bad", 'echo "$1:1: wrong"; exit 1\n', check=()),
            self.tool("good", "echo fine\n", check=()),
        )
        self.write("a.md")
        code, output = self.lint(tools, ["a.md"])
        self.assertEqual(1, code)
        self.assertIn("a.md:1: wrong", output)
        self.assertIn("bad", output)
        self.assertNotIn("fine", output)

    def test_fails_when_a_tool_cannot_check(self) -> None:
        self.write("a.md")
        code, output = self.lint((self.tool("broken", "exit 2\n", check=()),), ["a.md"])
        self.assertEqual(2, code)
        self.assertIn("broken exited with 2", output)

    def test_fix_runs_the_tools_that_fix_and_only_those(self) -> None:
        tools = (self.tool("linter", check=()), self.tool("formatter", fix=("fmt",)))
        self.write("a.md")
        self.assertEqual(0, self.lint(tools, ["a.md"], fix=True)[0])
        self.assertEqual(["fmt", "a.md"], self.recorded("formatter"))
        self.assertEqual([], self.recorded("linter"))
        self.assertEqual(0, self.lint(tools, ["a.md"])[0])
        self.assertEqual(["a.md"], self.recorded("linter"))
        self.assertEqual(["fmt", "a.md"], self.recorded("formatter"))

    def test_leaves_out_files_that_do_not_exist(self) -> None:
        self.write("a.md")
        self.assertEqual(
            0, self.lint((self.tool("md", check=()),), ["a.md", "gone.md"])[0]
        )
        self.assertEqual(["a.md"], self.recorded("md"))

    def test_the_repository_s_tools_each_check_or_fix(self) -> None:
        names = [tool.name for tool in TOOLS]
        self.assertEqual(len(names), len(set(names)))
        for tool in TOOLS:
            self.assertTrue(tool.check is not None or tool.fix is not None, tool.name)


if __name__ == "__main__":
    unittest.main()
