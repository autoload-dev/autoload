"""Check loaded add-on dependencies and physical inputs without guessing filenames."""

import unittest
from collections.abc import Mapping

from tools.conventions.context import Call, Context, Location
from tools.conventions.rules.rg011 import AddonIndependence
from tools.conventions.test_support import Record, RepositoryTest

ROOT = "examples/addons/widget"
BUILD = ROOT + "/BUILD.bazel"


class AddonIndependenceTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write_consumer_modules()

    def context_for(
        self,
        records: list[Record],
        extra: tuple[str, ...] = (),
        sources: Mapping[str, str] | None = None,
    ) -> Context:
        paths = {record["path"] for record in records} | set(extra) | {BUILD}
        for name in paths:
            self.write(name, "")
        calls = tuple(
            Call(Location(name, 1), "rule", frozenset({"name"}), "entry")
            for name in sorted({record["path"] for record in records})
        )
        return self.context(calls=calls, records=records, sources=sources)

    def implementation(self) -> Record:
        return {
            "name": "//examples/addons/widget:library",
            "path": BUILD,
            "booleans": {"testonly": False},
        }

    def test_production_rejects_demo_targets_and_leaves_test_inputs_to_rg012(
        self,
    ) -> None:
        unit = self.implementation()
        unit["label_lists"] = {
            "deps": ["//examples/addons/widget/demo:resources"],
            "srcs": ["//examples/addons/widget:tests/hidden.cc"],
        }
        records: list[Record] = [
            unit,
            {
                "name": "//examples/addons/widget/demo:resources",
                "path": ROOT + "/demo/BUILD.bazel",
            },
        ]
        context = self.context_for(
            records,
            sources={
                "//examples/addons/widget:tests/hidden.cc": ROOT + "/tests/hidden.cc"
            },
        )
        findings = list(AddonIndependence().evaluate(context))
        self.assertEqual(
            [(BUILD, True)],
            [(item.location.path, "demo:resources" in item.message) for item in findings],
        )

    def test_visibility_is_not_a_consumer_dependency_and_test_tools_can_use_suites(
        self,
    ) -> None:
        unit = self.implementation()
        unit["label_lists"] = {"visibility": ["//examples/addons/widget/demo:group"]}
        check = self.implementation()
        check["name"] = "//examples/addons/widget:check"
        check["booleans"] = {"testonly": True}
        check["label_lists"] = {"deps": ["//examples/addons/widget/demo:group"]}
        records: list[Record] = [
            unit,
            check,
            {
                "name": "//examples/addons/widget/demo:group",
                "path": ROOT + "/demo/BUILD.bazel",
            },
        ]
        context = self.context_for(records)
        self.assertEqual([], list(AddonIndependence().evaluate(context)))

    def test_alias_entry_is_checked_and_macro_helpers_report_one_authored_input(
        self,
    ) -> None:
        alias = self.implementation()
        alias["kind"] = "alias"
        alias["labels"] = {"actual": "//examples/addons/widget/demo:suite"}
        helper = self.implementation()
        helper["name"] = "//examples/addons/widget:generated_helper"
        helper["labels"] = alias["labels"]
        records: list[Record] = [
            alias,
            helper,
            {
                "name": "//examples/addons/widget/demo:suite",
                "path": ROOT + "/demo/BUILD.bazel",
            },
        ]
        findings = list(AddonIndependence().evaluate(self.context_for(records)))
        self.assertEqual(len(findings), 1)

    def test_source_labels_resolve_to_their_physical_file(self) -> None:
        unit = self.implementation()
        unit["name"] = "//addons/widget:library"
        unit["label_keyed_strings"] = {
            "resource_paths": {"//addons/widget:demo/image.svg": "images/demo.svg"}
        }
        context = self.context_for(
            [unit],
            ("examples/MODULE.bazel",),
            {"//addons/widget:demo/image.svg": ROOT + "/demo/image.svg"},
        )
        findings = list(AddonIndependence().evaluate(context))
        self.assertEqual(len(findings), 1)
        self.assertIn("//addons/widget:demo/image.svg", findings[0].message)

    def test_workspace_module_inputs_are_resolved_and_external_ones_skipped(self) -> None:
        unit = self.implementation()
        # External repositories cannot be a demo, so only workspace modules resolve.
        unit["label_lists"] = {"srcs": ["@consumer//:fixture.gd", "@engine//:api.h"]}
        context = self.context_for(
            [unit],
            ("consumer/MODULE.bazel", "consumer/BUILD.bazel"),
            {"@consumer//:fixture.gd": ROOT + "/demo/fixture.gd"},
        )
        findings = list(AddonIndependence().evaluate(context))
        self.assertEqual(len(findings), 1)
        self.assertIn("@consumer//:fixture.gd", findings[0].message)

    def test_regression_addons_get_the_same_boundary_check_without_opt_in(self) -> None:
        root = "scenarios/shared_addon/widget"
        unit: Record = {
            "name": "//tests/shared_addon/widget:widget",
            "path": root + "/BUILD.bazel",
            "booleans": {"testonly": False},
            "label_lists": {"deps": ["//tests/shared_addon/widget/demo:files"]},
        }
        demo: Record = {
            "name": "//tests/shared_addon/widget/demo:files",
            "path": root + "/demo/BUILD.bazel",
        }
        self.assertEqual(
            len(list(AddonIndependence().evaluate(self.context_for([unit, demo])))), 1
        )

    def test_missing_effective_role_is_not_a_compliance_result(self) -> None:
        unit = self.implementation()
        del unit["booleans"]
        findings = list(AddonIndependence().evaluate(self.context_for([unit])))
        self.assertEqual([item.status for item in findings], ["not_checked"])

    def test_source_symlink_cannot_hide_a_demo_input(self) -> None:
        unit = self.implementation()
        unit["label_lists"] = {"srcs": ["//examples/addons/widget:borrowed.cc"]}
        self.write(ROOT + "/demo/source.cc", "")
        self.write(ROOT + "/borrowed.cc", "")
        source = self.root / ROOT / "borrowed.cc"
        source.unlink()
        source.symlink_to(self.root / ROOT / "demo/source.cc")
        context = self.context_for(
            [unit],
            sources={"//examples/addons/widget:borrowed.cc": ROOT + "/borrowed.cc"},
        )
        self.assertEqual(len(list(AddonIndependence().evaluate(context))), 1)


if __name__ == "__main__":
    unittest.main()
