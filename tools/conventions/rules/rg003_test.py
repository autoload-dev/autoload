"""RG003 regressions for explicit names and actual target-producing calls."""

import unittest

from tools.conventions.context import Call, Location
from tools.conventions.rules.rg003 import ExplicitNames
from tools.conventions.test_support import Record, RepositoryTest


class ExplicitNamesTest(RepositoryTest):
    def test_only_calls_proven_to_produce_targets_require_a_name(self) -> None:
        calls = tuple(
            Call(Location("BUILD.bazel", line), kind, frozenset())
            for line, kind in (
                (1, "package"),
                (2, "exports_files"),
                (3, "helper"),
                (4, "custom"),
            )
        )
        records: list[Record] = [
            {
                "name": "//:hidden",
                "path": "BUILD.bazel",
                "line": 4,
                "strings": {"generator_function": "custom"},
            }
        ]
        findings = list(ExplicitNames().evaluate(self.context(calls, records)))
        self.assertEqual([4], [item.location.line for item in findings])
        self.assertEqual("custom must pass name explicitly", findings[0].message)

    def test_computed_name_is_still_explicit(self) -> None:
        calls = (Call(Location("BUILD.bazel", 1), "custom", frozenset({"name"})),)
        records: list[Record] = [
            {
                "name": "//:computed_name",
                "path": "BUILD.bazel",
                "strings": {"generator_function": "custom"},
            }
        ]
        self.assertEqual([], list(ExplicitNames().evaluate(self.context(calls, records))))


if __name__ == "__main__":
    unittest.main()
