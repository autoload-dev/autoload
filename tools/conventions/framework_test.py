"""Framework regressions for independent selection, rule results and shared tools."""

import unittest
from collections.abc import Iterable

from tools.conventions.context import Call, Context, Location
from tools.conventions.framework import Finding, RuleInfo, run
from tools.conventions.registry import select
from tools.conventions.rules.rg002 import TargetNames
from tools.conventions.rules.rg003 import ExplicitNames
from tools.conventions.test_support import RepositoryTest


class AdditionalRule:
    info = RuleInfo("RG999", "An independent rule")

    def evaluate(self, context: Context) -> Iterable[Finding]:
        yield Finding(Location("BUILD.bazel", 3), "requires review", "not_checked")
        yield Finding(Location("BUILD.bazel", 2), "a violation")


class RepeatingRule(AdditionalRule):
    def evaluate(self, context: Context) -> Iterable[Finding]:
        yield from super().evaluate(context)
        yield Finding(Location("BUILD.bazel", 2), "a violation")


class FrameworkTest(RepositoryTest):
    def test_additional_rule_returns_uniform_results_without_checker_changes(
        self,
    ) -> None:
        report = run(self.context(), (AdditionalRule(),))
        self.assertEqual(1, len(report.violations))
        self.assertEqual(1, len(report.not_checked))
        self.assertEqual("RG999", report.violations[0].rule.id)
        self.assertEqual(
            "BUILD.bazel:2: RG999: a violation (rules_godot/docs/public/conventions.md#rg999)",
            str(report.violations[0]),
        )
        self.assertIn("RG999 not checked", str(report.not_checked[0]))

    def test_required_incomplete_coverage_blocks_only_its_own_gate(self) -> None:
        class RequiredRule(AdditionalRule):
            def evaluate(self, context: Context) -> Iterable[Finding]:
                yield Finding(
                    Location("BUILD.bazel", 1),
                    "missing evaluated evidence",
                    "not_checked",
                    required=True,
                )

        report = run(self.context(), (RequiredRule(),))
        self.assertEqual(1, len(report.failures))
        self.assertEqual(0, len(report.violations))
        ordinary = run(self.context(), (AdditionalRule(),))
        self.assertEqual(ordinary.violations, ordinary.failures)

    def test_selected_rule_does_not_load_unneeded_tools(self) -> None:
        report = run(self.context(), select(["RG001"]))
        self.assertFalse(report.diagnostics)
        self.assertEqual((0, 0), (self.tools.call_requests, self.tools.rule_requests))

    def test_rules_share_the_same_declaration_data(self) -> None:
        call = Call(
            Location("BUILD.bazel", 1), "filegroup", frozenset({"name"}), "bad-name"
        )
        context = self.context((call,), [{"name": "//:bad-name", "path": "BUILD.bazel"}])
        report = run(context, (TargetNames({}), ExplicitNames()))
        self.assertEqual(["RG002"], [item.rule.id for item in report.violations])
        self.assertEqual((1, 1), (self.tools.call_requests, self.tools.rule_requests))

    def test_repeated_findings_are_a_rule_defect(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate convention findings"):
            run(self.context(), (RepeatingRule(),))

    def test_duplicate_or_unknown_ids_fail_before_running_rules(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be unique"):
            run(self.context(), (AdditionalRule(), AdditionalRule()))
        with self.assertRaisesRegex(ValueError, "Unknown convention rule IDs"):
            select(["RG999"])
        with self.assertRaisesRegex(ValueError, "Unknown convention rule IDs"):
            select(exclude=["RG999"])

    def test_complementary_selection_checks_every_rule_once(self) -> None:
        selected = ["RG004", "RG006", "RG013"]
        included = {rule.info.id for rule in select(selected)}
        excluded = {rule.info.id for rule in select(exclude=selected)}
        self.assertFalse(included & excluded)
        self.assertEqual(included | excluded, {rule.info.id for rule in select()})
        self.assertEqual(select(["RG004"], ["RG004"]), ())


if __name__ == "__main__":
    unittest.main()
