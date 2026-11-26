"""The contract checks over declared evidence."""

import json
import unittest

from tools.docs.contracts import behavior_errors, check_cases
from tools.docs.evidence import Evidence, Labels, decode_configured, decode_loading
from tools.docs.output_contracts import Api, parse

DOC = """
Build a thing.

### Default outputs
- files (one): build

### Generated targets
- `{name}.boundary` (files): Check a separately analyzed operation
"""

API = Api("macro_info", parse(DOC), "//:defs.bzl")

LOADING = """<query version="2">
    <rule class="thing" location="BUILD.bazel:1:1" name="//:a">
        <string name="generator_location" value="BUILD.bazel:1:1"/>
        <list name="visibility"><label value="//visibility:public"/></list>
    </rule>
    <rule class="filegroup" location="BUILD.bazel:1:1" name="//:a.boundary">
        <string name="generator_location" value="BUILD.bazel:1:1"/>
        <list name="visibility"><label value="//visibility:public"/></list>
    </rule>
</query>"""


def evidence(settings: dict[str, str], *labels: str) -> Evidence:
    facts = [
        {
            "label": label,
            "files": 1,
            "runfiles": 0,
            "executable": False,
            "providers": [],
            "groups": [],
        }
        for label in labels
    ]
    return Evidence(
        decode_loading(LOADING, Labels({})),
        (decode_configured(json.dumps({"settings": settings, "facts": facts})),),
    )


def case(**fields: object) -> dict:
    return (
        {"target": "//:a", "companions": ["{name}.boundary"], "conditions": []}
        | {"settings": {}}
        | fields
    )


class CheckCasesTest(unittest.TestCase):
    def test_a_case_with_its_companion_in_its_configuration_matches(self) -> None:
        settings = {"//command_line_option:platforms": "//:android"}
        facts = evidence(settings, "//:a", "//:a.boundary")
        self.assertEqual(
            {"//:defs.bzl%a": []},
            check_cases(facts, {"//:defs.bzl%a": (case(settings=settings), API)}),
        )

    def test_a_case_must_analyze_its_documented_companions(self) -> None:
        facts = evidence({}, "//:a")
        self.assertEqual(
            {
                "//:defs.bzl%a": [
                    (
                        "//:defs.bzl%a: the case does not analyze its companion"
                        " {name}.boundary"
                    )
                ]
            },
            check_cases(facts, {"//:defs.bzl%a": (case(companions=[]), API)}),
        )


class BehaviorErrorsTest(unittest.TestCase):
    def test_registered_behavior_tests_must_be_evaluated_tests(self) -> None:
        behavior = {"//:defs.bzl%a": ["//:a_test", "//:gone_test"]}
        self.assertEqual(
            ["unresolved evaluated behavior test: //:gone_test"],
            behavior_errors(behavior, {"//:a_test"}),
        )


if __name__ == "__main__":
    unittest.main()
