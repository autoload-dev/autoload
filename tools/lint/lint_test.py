"""Tests of how the linters pick their files and read Buildifier's report."""

import unittest

from tools.lint.lint import buildifier_findings, is_starlark, is_workflow, select


class SelectionTest(unittest.TestCase):
    def test_each_linter_sees_only_its_own_files(self) -> None:
        paths = [
            "tools/ci/work.py",
            "rules_godot/godot/defs.bzl",
            "rules_godot/godot/BUILD.bazel",
            "MODULE.bazel",
            ".github/workflows/ci.yml",
            ".github/actions/setup/action.yml",
            "README.md",
        ]
        self.assertEqual(
            [
                "rules_godot/godot/defs.bzl",
                "rules_godot/godot/BUILD.bazel",
                "MODULE.bazel",
            ],
            select(paths, is_starlark),
        )
        self.assertEqual([".github/workflows/ci.yml"], select(paths, is_workflow))


class BuildifierReportTest(unittest.TestCase):
    def test_lint_warnings_count_and_formatting_does_not(self) -> None:
        report = {
            "files": [
                {"filename": "unformatted.bzl", "formatted": False, "valid": True},
                {
                    "filename": "a.bzl",
                    "formatted": True,
                    "valid": True,
                    "warnings": [
                        {
                            "start": {"line": 1, "column": 1},
                            "category": "module-docstring",
                            "message": "The file has no module docstring.",
                            "url": "https://example.com/module-docstring",
                        }
                    ],
                },
                {"filename": "broken.bzl", "formatted": False, "valid": False},
            ]
        }
        self.assertEqual(
            [
                "broken.bzl: not valid Starlark",
                (
                    "a.bzl:1: module-docstring: The file has no module docstring. "
                    "(https://example.com/module-docstring)"
                ),
            ],
            buildifier_findings(report),
        )


if __name__ == "__main__":
    unittest.main()
