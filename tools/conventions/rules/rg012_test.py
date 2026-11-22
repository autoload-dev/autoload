"""Production targets anywhere must not consume inputs owned by a tests/ scope."""

import unittest
from collections.abc import Mapping
from pathlib import Path

from tools.conventions.context import Call, Context, Location
from tools.conventions.rules.rg012 import ProductionIsolation, test_scope
from tools.conventions.test_support import Record, RepositoryTest

# A regression project of the consumer module at tests/: its labels are module-relative.
APP = "rules_godot/tests/projects/game"
LABEL = "//projects/game"


def rule(
    label: str, path: str, testonly: bool | None = False, **lists: list[str]
) -> Record:
    record: Record = {"name": label, "path": path}
    if testonly is not None:
        record["booleans"] = {"testonly": testonly}
    if lists:
        record["label_lists"] = dict(lists)
    return record


class ProductionIsolationTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write_consumer_modules()

    def evaluate(
        self, records: list[Record], sources: Mapping[str, str] | None = None
    ) -> list[tuple[str, str]]:
        for name in {record["path"] for record in records} | set(
            (sources or {}).values()
        ):
            self.write(name, "")
        calls = tuple(
            Call(Location(name, 1), "rule", frozenset({"name"}), "entry")
            for name in sorted({record["path"] for record in records})
        )
        context: Context = self.context(calls=calls, records=records, sources=sources)
        return [
            (item.status, item.location.path)
            for item in ProductionIsolation().evaluate(context)
        ]

    def test_application_content_must_not_consume_its_test_suites(self) -> None:
        main = rule(
            f"{LABEL}/main:main",
            f"{APP}/main/BUILD.bazel",
            deps=[f"{LABEL}/tests:suites"],
        )
        suites = rule(f"{LABEL}/tests:suites", f"{APP}/tests/BUILD.bazel", testonly=True)
        self.assertEqual(
            [("violation", f"{APP}/main/BUILD.bazel")], self.evaluate([main, suites])
        )

    def test_test_only_consumers_and_test_scope_declarations_may_use_tests(self) -> None:
        check = rule(
            f"{LABEL}:check",
            f"{APP}/BUILD.bazel",
            testonly=True,
            deps=[f"{LABEL}/tests:suites"],
        )
        test = rule(
            f"{LABEL}/tests:tests",
            f"{APP}/tests/BUILD.bazel",
            srcs=[f"{LABEL}/tests:helper.gd"],
        )
        self.assertEqual(
            [],
            self.evaluate(
                [check, test], {f"{LABEL}/tests:helper.gd": f"{APP}/tests/helper.gd"}
            ),
        )

    def test_generated_test_outputs_count_by_their_package(self) -> None:
        main = rule(
            f"{LABEL}/main:main",
            f"{APP}/main/BUILD.bazel",
            srcs=[f"{LABEL}/tests:generated.gd"],
        )
        self.write(f"{APP}/main/BUILD.bazel", "")
        calls = (
            Call(
                Location(f"{APP}/main/BUILD.bazel", 1),
                "rule",
                frozenset({"name"}),
                "entry",
            ),
        )
        context = self.context(
            calls=calls, records=[main], generated=(f"{LABEL}/tests:generated.gd",)
        )
        self.assertEqual(
            ["violation"],
            [item.status for item in ProductionIsolation().evaluate(context)],
        )

    def test_shared_regression_fixtures_are_not_a_test_scope(self) -> None:
        main = rule(
            f"{LABEL}:project",
            f"{APP}/BUILD.bazel",
            deps=["//support/native:hello"],
        )
        fixture = rule(
            "//support/native:hello", "rules_godot/tests/support/native/BUILD.bazel"
        )
        self.assertEqual([], self.evaluate([main, fixture]))

    def test_test_scopes_are_measured_from_the_owning_module(self) -> None:
        workspace = self.workspace()
        for name, expected in (
            ("rules_godot/tests/support/x/BUILD.bazel", False),
            ("rules_godot/tests/BUILD.bazel", False),
            ("rules_godot/tests/projects/y/BUILD.bazel", False),
            ("rules_godot/tests/projects/y/tests/BUILD.bazel", True),
            ("rules_godot/tests/projects/y/tests/android/BUILD.bazel", True),
            ("godot/private/tests/BUILD.bazel", True),
            ("godot/private/BUILD.bazel", False),
            (
                "rules_godot/examples/addons/widget/native/backends/linux/tests/fixture.gd",
                True,
            ),
        ):
            with self.subTest(name=name):
                self.assertEqual(expected, test_scope(workspace, Path(name)))

    def test_add_on_demo_must_not_consume_add_on_test_sources(self) -> None:
        root = "rules_godot/examples/addons/widget"
        demo = rule(
            f"//{root}/demo:demo",
            f"{root}/demo/BUILD.bazel",
            srcs=[f"//{root}/demo:fixture.gd"],
        )
        source = {
            f"//{root}/demo:fixture.gd": f"{root}/native/backends/linux/tests/fixture.gd"
        }
        self.assertEqual(
            [("violation", f"{root}/demo/BUILD.bazel")], self.evaluate([demo], source)
        )

    def test_visibility_and_external_labels_are_not_inputs(self) -> None:
        main = rule(
            f"{LABEL}/main:main",
            f"{APP}/main/BUILD.bazel",
            visibility=[f"{LABEL}/tests:__pkg__"],
            deps=["@engine//tests:fixture"],
        )
        self.assertEqual([], self.evaluate([main]))

    def test_missing_effective_role_is_not_a_compliance_result(self) -> None:
        main = rule(f"{LABEL}/main:main", f"{APP}/main/BUILD.bazel", testonly=None)
        self.assertEqual(
            [("not_checked", f"{APP}/main/BUILD.bazel")], self.evaluate([main])
        )


if __name__ == "__main__":
    unittest.main()
