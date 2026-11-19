"""RG002 regressions for authored names, generated helpers and artifact identity."""

import unittest

from tools.conventions.context import Call, Location
from tools.conventions.rules.rg002 import TargetNames
from tools.conventions.test_support import Record, RepositoryTest


class TargetNamesTest(RepositoryTest):
    def test_literal_root_checks_every_nested_generated_helper(self) -> None:
        calls = (
            Call(Location("BUILD.bazel", 1), "godot_custom", frozenset({"name"}), "good"),
        )
        records: list[Record] = [
            {
                "name": "//:good.check",
                "path": "BUILD.bazel",
                "strings": {"generator_function": "godot_custom"},
                "owner": "//godot:custom.bzl%godot_custom",
            },
            {
                "name": "//:good__helper",
                "path": "BUILD.bazel",
                "strings": {"generator_function": "godot_custom"},
                "owner": "//godot:custom.bzl%godot_custom",
            },
        ]
        self.assertEqual(
            ["violation"],
            [
                item.status
                for item in TargetNames({}).evaluate(self.context(calls, records))
            ],
        )

    def test_test_suites_of_tests_packages_name_tests_after_functions(self) -> None:
        calls = (
            Call(
                Location("BUILD.bazel", 1),
                "pack_test_suite",
                frozenset({"name"}),
                "pack_test_suite",
            ),
        )
        records: list[Record] = [
            {
                "name": "//:" + name,
                "path": "BUILD.bazel",
                "strings": {"generator_function": "pack_test_suite"},
                "owner": "//godot/private/tests:pack_tests.bzl%pack_test_suite",
            }
            for name in ("pack_test_suite", "test_pack_reads_declared_imports")
        ]
        self.assertEqual([], list(TargetNames({}).evaluate(self.context(calls, records))))

    def test_dotted_helpers_stay_with_the_complete_authored_root(self) -> None:
        call = Call(
            Location("BUILD.bazel", 1), "godot_binary", frozenset({"name"}), "game_debug"
        )
        for emitted, accepted in (
            ("game_debug.project.imports", True),
            ("game.debug.project", False),
            ("game_debug.project__imports", False),
        ):
            records: list[Record] = [
                {
                    "name": "//:" + emitted,
                    "path": "BUILD.bazel",
                    "strings": {"generator_function": "godot_binary"},
                    "owner": "//godot/private:run.bzl%godot_binary",
                }
            ]
            self.assertEqual(
                accepted,
                not list(TargetNames({}).evaluate(self.context((call,), records))),
            )

    def test_unresolved_owned_computed_root_requires_coverage(self) -> None:
        call = Call(Location("BUILD.bazel", 1), "godot_binary", frozenset({"name"}))
        records: list[Record] = [
            {
                "name": "//:game.project",
                "path": "BUILD.bazel",
                "strings": {
                    "generator_function": "godot_binary",
                    "generator_name": "game.project",
                },
                "owner": "//godot/private:run.bzl%godot_binary",
            }
        ]
        findings = list(TargetNames({}).evaluate(self.context((call,), records)))
        self.assertEqual([True], [item.required for item in findings])

    def test_mobile_basename_roles_may_repeat_the_root_after_a_slash(self) -> None:
        call = Call(Location("BUILD.bazel", 1), "godot_app", frozenset({"name"}), "app")
        for emitted, accepted in (
            ("app.android_apk/app.godot_bootstrap.java", True),
            ("app.ios/app", True),
            ("app.ios/other", False),
            ("app.android_apk/App", False),
        ):
            records: list[Record] = [
                {
                    "name": "//:" + emitted,
                    "path": "BUILD.bazel",
                    "strings": {"generator_function": "godot_app"},
                    "owner": "//godot:app.bzl%godot_app",
                }
            ]
            findings = list(TargetNames({}).evaluate(self.context((call,), records)))
            self.assertEqual(accepted, not findings, emitted)

    def test_full_target_name_uses_strict_spelling(self) -> None:
        for name in (
            "Upper",
            "a-b",
            "a__b",
            "_leading",
            "trailing_",
            "1number",
            "café",
            "nested/path",
            "file.json",
        ):
            calls = (
                Call(Location("BUILD.bazel", 1), "filegroup", frozenset({"name"}), name),
            )
            findings = list(
                TargetNames({}).evaluate(
                    self.context(calls, [{"name": "//:" + name, "path": "BUILD.bazel"}])
                )
            )
            self.assertEqual(["violation"], [item.status for item in findings], name)
            self.assertIn(repr(name), findings[0].message)

    def test_computed_evaluated_name_is_checked_and_macro_name_remains_unknown(
        self,
    ) -> None:
        calls = (
            Call(Location("BUILD.bazel", 1), "filegroup", frozenset({"name"})),
            Call(Location("BUILD.bazel", 2), "custom", frozenset({"name"})),
        )
        records: list[Record] = [
            {"name": "//:bad-name", "path": "BUILD.bazel"},
            {
                "name": "//:computed_name__helper",
                "path": "BUILD.bazel",
                "line": 2,
                "strings": {"generator_function": "custom"},
            },
        ]
        findings = list(TargetNames({}).evaluate(self.context(calls, records)))
        self.assertEqual(
            [(1, "violation"), (2, "not_checked")],
            [(item.location.line, item.status) for item in findings],
        )

    def test_macro_fanout_reports_one_review_and_review_records_must_match(
        self,
    ) -> None:
        call = Call(Location("BUILD.bazel", 1), "custom", frozenset({"name"}))
        records: list[Record] = [
            {
                "name": "//:" + name,
                "path": "BUILD.bazel",
                "strings": {"generator_function": "custom"},
            }
            for name in ("computed", "computed.helper")
        ]
        context = self.context((call,), records)
        reviewed = {"BUILD.bazel": (("computed",),)}
        self.assertEqual(
            ["not_checked"],
            [item.status for item in TargetNames({}).evaluate(context)],
        )
        self.assertEqual([], list(TargetNames(reviewed).evaluate(context)))
        stale = list(TargetNames({"BUILD.bazel": (("gone",),)}).evaluate(context))
        self.assertEqual(["not_checked", "violation"], [item.status for item in stale])
        # A changed root, e.g. from a changed comprehension list, needs a new review.
        records[0]["name"] = "//:renamed"
        changed = self.context((call,), records)
        self.assertEqual(
            ["not_checked", "violation"],
            [item.status for item in TargetNames(reviewed).evaluate(changed)],
        )

    def test_artifact_qualification_requires_a_shared_binary(self) -> None:
        for kind, shared, count in (
            ("cc_binary", True, 0),
            ("cc_binary", False, 1),
            ("filegroup", True, 1),
        ):
            calls = (
                Call(
                    Location("BUILD.bazel", 1), kind, frozenset({"name"}), "libnative.so"
                ),
            )
            records: list[Record] = [
                {
                    "name": "//:libnative.so",
                    "path": "BUILD.bazel",
                    "booleans": {"linkshared": shared},
                }
            ]
            self.assertEqual(
                count,
                len(list(TargetNames({}).evaluate(self.context(calls, records)))),
            )


if __name__ == "__main__":
    unittest.main()
