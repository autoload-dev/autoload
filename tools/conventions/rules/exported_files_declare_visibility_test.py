"""Regressions for exports_files calls that state their visibility."""

import unittest

from tools.conventions.context import Call, Location
from tools.conventions.rules.exported_files_declare_visibility import (
    ExportedFilesDeclareVisibility,
)
from tools.conventions.test_support import RepositoryTest


def call(kind: str, *attrs: str) -> Call:
    return Call(Location("tools/BUILD.bazel", 3), kind, frozenset(attrs), "")


class ExportedFilesDeclareVisibilityTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write("MODULE.bazel", "")
        self.write("tools/BUILD.bazel", "")

    def findings(self, *calls: Call) -> list[str]:
        context = self.context(calls=calls)
        return [
            f"{item.location.path}:{item.location.line}"
            for item in ExportedFilesDeclareVisibility().evaluate(context)
        ]

    def test_exports_with_a_visibility_pass(self) -> None:
        self.assertEqual(self.findings(call("exports_files", "visibility")), [])

    def test_exports_without_a_visibility_are_reported(self) -> None:
        self.assertEqual(self.findings(call("exports_files")), ["tools/BUILD.bazel:3"])

    def test_other_calls_without_a_visibility_pass(self) -> None:
        self.assertEqual(self.findings(call("filegroup", "name", "srcs")), [])


if __name__ == "__main__":
    unittest.main()
