"""Regressions for the godot_process tag of the tests that start a Godot process."""

import unittest

from tools.conventions.rules.godot_process_tests_tagged import TAG, GodotProcessTests
from tools.conventions.test_support import Record, RepositoryTest

GODOT = "//tests:exports_test"


def test(name: str, *tags: str, line: int = 1) -> Record:
    return {
        "name": f"//tests:{name}",
        "path": "tests/BUILD.bazel",
        "line": line,
        "kind": "py_test",
        "string_lists": {"tags": list(tags)},
    }


class GodotProcessTestsTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write("tests/BUILD.bazel", "")

    def findings(self, *records: Record, godot: frozenset[str]) -> list[str]:
        context = self.context(records=list(records))
        self.tools.dependents = godot
        return [
            f"{item.location.line}: {item.message}"
            for item in GodotProcessTests().evaluate(context)
        ]

    def test_tagged_godot_tests_and_untagged_others_pass(self) -> None:
        self.assertEqual(
            self.findings(
                test("exports_test", TAG),
                test("unit_test", line=2),
                godot=frozenset({GODOT}),
            ),
            [],
        )

    def test_a_godot_test_without_the_tag_is_reported(self) -> None:
        self.assertEqual(
            self.findings(test("exports_test"), godot=frozenset({GODOT})),
            [f"1: //tests:exports_test starts a Godot process: tag it {TAG}"],
        )

    def test_the_tag_on_a_test_without_godot_is_reported(self) -> None:
        self.assertEqual(
            self.findings(test("unit_test", TAG), godot=frozenset()),
            [f"1: //tests:unit_test starts no Godot process: remove {TAG}"],
        )

    def test_godot_test_tags_its_tests_itself(self) -> None:
        # godot_test adds the tag unless the test is a smoke test; the rule leaves it out.
        godot_test = test("exports_test") | {"kind": "_godot_test"}
        self.assertEqual(self.findings(godot_test, godot=frozenset({GODOT})), [])

    def test_targets_a_macro_tags_beside_its_test_are_not_tests(self) -> None:
        view: Record = {
            "name": "//tests:exports_test.view",
            "path": "tests/BUILD.bazel",
            "kind": "godot_view",
            "string_lists": {"tags": [TAG]},
        }
        self.assertEqual(
            self.findings(test("exports_test", TAG), view, godot=frozenset({GODOT})),
            [],
        )

    def test_a_smoke_test_runs_with_the_fast_tests(self) -> None:
        self.assertEqual(
            self.findings(test("exports_test", "smoke"), godot=frozenset({GODOT})),
            [],
        )
        self.assertEqual(
            self.findings(test("exports_test", "smoke", TAG), godot=frozenset({GODOT})),
            [
                (
                    f"1: //tests:exports_test is a smoke test, which runs with the fast "
                    f"tests: remove {TAG}"
                )
            ],
        )

    def test_analysis_tests_and_manual_tests_are_exempt(self) -> None:
        self.assertEqual(
            self.findings(
                test("exports_test", "starlark_analysis_test"),
                test("fixture_test", "manual", line=2),
                test("source_built_test", "source_engine", line=3),
                godot=frozenset(
                    {GODOT, "//tests:fixture_test", "//tests:source_built_test"}
                ),
            ),
            [],
        )

    def test_registry_test_modules_are_not_checked(self) -> None:
        self.write("rules_godot/MODULE.bazel", "")
        self.write("rules_godot/.bazelignore", "bcr\n")
        self.write(".bazelignore", "rules_godot\n")
        self.write("rules_godot/bcr/smoke/MODULE.bazel", "")
        self.write("rules_godot/bcr/smoke/BUILD.bazel", "")
        record: Record = {
            "name": "//:smoke_test",
            "path": "rules_godot/bcr/smoke/BUILD.bazel",
            "kind": "build_test",
        }
        self.assertEqual(self.findings(record, godot=frozenset({"//:smoke_test"})), [])


if __name__ == "__main__":
    unittest.main()
