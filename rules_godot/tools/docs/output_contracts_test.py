"""Rejection tests for source-owned output contracts and configured evidence."""

import unittest
from dataclasses import replace

from tools.docs.output_contracts import (
    Api,
    ConfiguredTarget,
    Contract,
    behavior_lane,
    compare,
    coverage_errors,
    has_consumer_visibility,
    kind_errors,
    parse,
    provider_identity,
)

DOC = """
An independently useful API.

### Default outputs
- files (one): build

### Output groups
- `debug_symbols`: detached
  symbols
  - availability: symbols

### Generated targets
- `{name}.debug_symbols` (alias): Avoid signer analysis
  - purpose: analysis_boundary
"""
FILES = ConfiguredTarget("//:app", 1, 0, False, frozenset(), frozenset())
EXECUTABLE = ConfiguredTarget("//:run", 1, 1, True, frozenset(), frozenset())


class OutputContractsTest(unittest.TestCase):
    def test_parses_entries_with_defaults_fields_and_continuations(self) -> None:
        contract = parse(DOC)
        self.assertEqual("detached symbols", contract.groups[0]["contents"])
        self.assertEqual("symbols", contract.groups[0]["availability"])
        self.assertEqual("none", contract.groups[0]["prerequisites"])
        companion = contract.companions[0]
        self.assertEqual("analysis_boundary", companion["purpose"])
        self.assertEqual(
            ("public", "false"), (companion["visibility"], companion["testonly"])
        )

    def test_omitted_sections_are_empty_and_default_outputs_required(self) -> None:
        contract = parse(DOC.split("### Output groups")[0])
        self.assertEqual(((), ()), (contract.groups, contract.companions))
        with self.assertRaisesRegex(ValueError, "Default outputs"):
            parse(DOC.replace("### Default outputs", "### Removed"))
        with self.assertRaisesRegex(ValueError, "omitted"):
            parse(DOC.split("### Output groups")[0] + "### Output groups\n")

    def test_rejects_invalid_entries_and_fields(self) -> None:
        for invalid in (
            DOC.replace("- files (one): build", "files (one): build"),
            DOC.replace("- files (one): build", "- files: build"),
            DOC.replace("  - availability: symbols", "  - unknown: symbols"),
            DOC.replace(
                "  - availability: symbols",
                "  - availability: symbols\n  - availability: other",
            ),
            DOC.replace(
                "  - availability: symbols",
                "  - availability: symbols\n- `debug_symbols`: again\n  - availability: symbols",
            ),
            DOC.replace("analysis_boundary", "file_subset"),
            DOC.replace("  - purpose: analysis_boundary", "  - purpose: test"),
            DOC.replace(
                "  - purpose: analysis_boundary",
                "  - purpose: analysis_boundary\n  - testonly: maybe",
            ),
            DOC.replace("Avoid signer analysis", "none"),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse(invalid)

    def test_behavior_tests_resolve_in_a_lane_that_evaluates_their_module(self) -> None:
        # The docs lane of the default hook evaluates the ruleset module only.
        self.assertEqual("docs", behavior_lane("."))
        self.assertEqual("desktop", behavior_lane("tests"))
        self.assertEqual("desktop", behavior_lane("examples"))

    def test_kind_semantics(self) -> None:
        test = replace(EXECUTABLE, label="//:test")
        library = replace(
            EXECUTABLE, providers=frozenset({"@@rules_cc+//cc:x.bzl%CcInfo"})
        )
        toolchain = replace(FILES, files=0, providers=frozenset({"ToolchainInfo"}))
        cases = [
            ("files", FILES, {}, []),
            ("files", EXECUTABLE, {}, ["undocumented executable behavior"]),
            ("executable", EXECUTABLE, {}, []),
            ("executable", FILES, {}, ["missing promised executable or runfiles"]),
            ("test", test, {"test": True}, []),
            ("test", EXECUTABLE, {}, ["promised test is not an evaluated Bazel test"]),
            (
                "files",
                test,
                {"test": True},
                [
                    "undocumented evaluated test behavior",
                    "undocumented executable behavior",
                ],
            ),
            ("metadata", FILES, {}, ["metadata must not produce default files"]),
            ("library", library, {"shared_library": True}, []),
            ("library", library, {}, ["undocumented executable behavior"]),
            ("library", FILES, {}, ["library lacks CcInfo"]),
            ("toolchain", toolchain, {}, []),
            (
                "toolchain",
                replace(toolchain, providers=frozenset()),
                {},
                ["toolchain lacks ToolchainInfo"],
            ),
        ]
        for kind, target, options, expected in cases:
            with self.subTest(kind=kind, target=target, options=options):
                arguments = {"test": False, **options}
                self.assertEqual(expected, kind_errors(kind, target, **arguments))

    def test_configured_comparison_is_bidirectional_and_conditional(self) -> None:
        good = replace(FILES, groups=frozenset({"debug_symbols", "_validation"}))

        def check(
            target: ConfiguredTarget,
            companions: frozenset[str] = frozenset({"{name}.debug_symbols"}),
            forwarded_groups: bool = False,
        ) -> list[str]:
            return compare(
                parse(DOC),
                target,
                test=False,
                companions=companions,
                conditions={"symbols"},
                forwarded_groups=forwarded_groups,
            )

        self.assertEqual([], check(good))
        self.assertEqual(
            [
                "missing documented group: debug_symbols",
                "undocumented group: report",
            ],
            check(replace(good, groups=frozenset({"report"}))),
        )
        forwarded = replace(good, groups=frozenset({"debug_symbols", "dossier"}))
        self.assertEqual([], check(forwarded, forwarded_groups=True))
        self.assertIn(
            "undocumented companion: {name}.extra",
            check(good, frozenset({"{name}.debug_symbols", "{name}.extra"})),
        )

    def test_provider_identities_drop_the_ruleset_repository(self) -> None:
        self.assertEqual(
            "//godot:a.bzl%A", provider_identity("@@autoload_rules_godot+//godot:a.bzl%A")
        )
        self.assertEqual(
            "//godot:a.bzl%A", provider_identity("@autoload_rules_godot//godot:a.bzl%A")
        )
        self.assertEqual(
            "@@rules_cc+//cc:x.bzl%CcInfo",
            provider_identity("@@rules_cc+//cc:x.bzl%CcInfo"),
        )

    def test_restricted_visibility_still_exports_an_interface(self) -> None:
        self.assertFalse(
            has_consumer_visibility("//game:helper", ["//visibility:private"])
        )
        self.assertFalse(has_consumer_visibility("//game:helper", ["//game:__pkg__"]))
        self.assertTrue(
            has_consumer_visibility(
                "//game:helper", ["//game:__pkg__"], symbolic_macro=True
            )
        )
        self.assertTrue(has_consumer_visibility("//game:helper", ["//consumer:__pkg__"]))
        self.assertTrue(
            has_consumer_visibility("//game:helper", ["//game:__subpackages__"])
        )


class CoverageTest(unittest.TestCase):
    def test_new_api_and_stale_cases_cannot_escape_coverage(self) -> None:
        api = Api("rule_info", parse(DOC), "")
        errors = coverage_errors({"new_api": api}, {"gone": {}}, {})
        self.assertIn("new_api: missing configured case", errors)
        self.assertIn("gone: case refers to unknown API", errors)
        self.assertIn(
            "new_api: public companions need a registered behavior test", errors
        )

    def test_conditions_and_case_kinds_need_matching_cases(self) -> None:
        api = Api("rule_info", parse(DOC), "")
        errors = coverage_errors(
            {"api": api},
            {"api": {"target": "//:a"}, "api#repo": {"entrypoints": {}}},
            {"api": ["//:test"]},
        )
        self.assertEqual(
            [
                "api: conditional availability 'symbols' has no configured case",
                "api#repo: repository APIs, and only those, use entrypoint cases",
            ],
            errors,
        )

    def test_functions_declaring_repositories_use_entrypoint_cases(self) -> None:
        helper = Api(
            "func_info",
            Contract(
                ({"kind": "repository", "cardinality": "none", "availability": "always"},)
            ),
            "",
        )
        self.assertEqual(
            [], coverage_errors({"helper": helper}, {"helper": {"entrypoints": {}}}, {})
        )
        errors = coverage_errors({"helper": helper}, {"helper": {"target": "//:a"}}, {})
        self.assertIn(
            "helper: repository APIs, and only those, use entrypoint cases", errors
        )


if __name__ == "__main__":
    unittest.main()
