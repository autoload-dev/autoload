"""Regressions for release archives that leave out the released modules' tests."""

import unittest

from tools.conventions.context import EvidenceError
from tools.conventions.rules.rg023 import ReleasedWithoutTests
from tools.conventions.test_support import RepositoryTest

EXCLUDED = "tests export-ignore\nbcr/**/tests -export-ignore\n"


class ReleasedWithoutTestsTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        for module in ("rules_godot", "addons/widget"):
            self.write(f"{module}/MODULE.bazel", 'module(name = "m")\n')
            self.write(f"{module}/.gitattributes", EXCLUDED)

    def findings(self) -> list[str]:
        return [
            f"{item.location.path}:{item.location.line}"
            for item in ReleasedWithoutTests().evaluate(self.context())
        ]

    def test_a_package_outside_tests_may_not_use_a_file_inside_them(self) -> None:
        self.write(
            "addons/widget/config/BUILD.bazel",
            'py_test(\n    name = "t",\n    srcs = ["tests/t.py"],\n'
            '    data = glob(["tests/testdata/*"]),\n)\n',
        )
        self.assertEqual(
            self.findings(),
            ["addons/widget/config/BUILD.bazel:3", "addons/widget/config/BUILD.bazel:4"],
        )

    def test_a_package_outside_tests_may_not_use_a_tests_package(self) -> None:
        self.write(
            "rules_godot/godot/BUILD.bazel",
            'filegroup(name = "all", srcs = ["//godot/private/tests:fixtures"])\n',
        )
        self.assertEqual(self.findings(), ["rules_godot/godot/BUILD.bazel:1"])

    def test_tests_and_what_never_loads_them_may_name_them(self) -> None:
        # The tests themselves, load and target visibility, and what only the module's own
        # builds evaluate: dev dependencies, which other modules ignore.
        self.write(
            "addons/widget/tests/BUILD.bazel",
            'cc_test(name = "t", srcs = ["t.cc"], data = ["//tests/fixtures:f"])\n',
        )
        self.write(
            "rules_godot/godot/private/paths.bzl",
            'visibility(["//godot", "//godot/private/tests"])\n',
        )
        self.write(
            "rules_godot/godot/BUILD.bazel",
            'package(default_visibility = ["//godot/private/tests:__pkg__"])\n'
            'package_group(name = "g", packages = ["//godot/private/tests/..."])\n'
            'filegroup(name = "f", visibility = ["//godot/tests:__subpackages__"])\n',
        )
        self.write(
            "rules_godot/MODULE.bazel",
            'module(name = "m")\n'
            'engines = use_extension("//:e.bzl", "e", dev_dependency = True)\n'
            'engines.source(patches = ["//godot/private/tests:p.patch"])\n'
            "local_repository(\n"
            '    name = "r",\n    dev_dependency = True,\n'
            '    path = "godot/private/tests/fixtures/r",\n)\n',
        )
        self.write(
            "rules_godot/godot/defs.bzl", '"""See the tests/ of each package."""\n'
        )
        self.assertEqual(self.findings(), [])

    def test_a_glob_may_exclude_tests(self) -> None:
        self.write(
            "addons/widget/BUILD.bazel",
            'filegroup(name = "f", srcs = glob(["**/*.py"], exclude = ["tests/**"]))\n',
        )
        self.assertEqual(self.findings(), [])

    def test_unparsable_starlark_is_evidence_error(self) -> None:
        self.write("addons/widget/BUILD.bazel", "filegroup(\n")
        with self.assertRaises(EvidenceError):
            self.findings()

    def test_the_release_archive_leaves_out_tests(self) -> None:
        self.write("rules_godot/.gitattributes", "docs export-ignore\n")
        self.assertEqual(
            self.findings(),
            ["rules_godot/.gitattributes:1", "rules_godot/.gitattributes:1"],
        )

    def test_the_registry_test_modules_keep_their_tests(self) -> None:
        # The registry runs them from the archive.
        self.write("addons/widget/.gitattributes", "tests export-ignore\n")
        self.assertEqual(self.findings(), ["addons/widget/.gitattributes:1"])

    def test_unreleased_modules_may_name_tests(self) -> None:
        self.write("e2e/rules_godot/BUILD.bazel", 'filegroup(srcs = ["tests/a"])\n')
        self.assertEqual(self.findings(), [])


if __name__ == "__main__":
    unittest.main()
