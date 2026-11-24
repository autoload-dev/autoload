"""Batching of the contract cases' evaluated Bazel facts."""

import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.docs.contracts import check_cases
from tools.docs.evidence import EvaluatedBazel
from tools.docs.output_contracts import Api, Contract

API = Api("rule", Contract(), "//:defs.bzl")


def case(target: str, options: tuple[str, ...] = ()) -> dict:
    return {"target": target, "module": ".", "options": list(options), "conditions": []}


def fake_bazel(command: list[str], _cwd: Path) -> str:
    """Answer a query with one rule per label and a cquery with one target per label."""
    if command[1] == "query":
        labels = re.findall(r"//[^ ()]+", command[2])
        rules = "".join(
            f'<rule class="genrule" name="{label}" location="BUILD.bazel:{line}:1"/>'
            for line, label in enumerate(labels, 1)
        )
        return "<query>" + rules + "</query>"
    scope = next(item for item in command if item.startswith("--universe_scope="))
    return "\n".join(
        json.dumps(
            {
                "label": "@@" + label,
                "files": 1,
                "runfiles": 0,
                "executable": False,
                "providers": [],
                "groups": [],
            }
        )
        for label in scope.partition("=")[2].split(",")
    )


class CheckCasesTest(unittest.TestCase):
    def test_one_query_and_one_cquery_per_group_ending_on_default_options(
        self,
    ) -> None:
        cases = {
            "//:defs.bzl%a": (case("//:a"), API),
            "//:defs.bzl%b": (case("//:b"), API),
            "//:defs.bzl%c": (case("//:c", ("--flag",)), API),
            "//:defs.bzl%d": (case("//:d", ("--flag",)), API),
        }
        with (
            patch("tools.docs.evidence.run_tool", side_effect=fake_bazel) as run,
            patch("tools.conventions.context.run_tool", side_effect=fake_bazel) as query,
        ):
            results = check_cases(EvaluatedBazel(Path("/workspace")), cases)
        # The empty contract's one diagnostic, attributed to each case's own key.
        self.assertEqual(
            {
                key: [f"{key}: require exactly one active default output contract"]
                for key in cases
            },
            results,
        )
        self.assertEqual(2, query.call_count)
        cquerys = [call.args[0] for call in run.call_args_list]
        self.assertEqual(2, len(cquerys))
        self.assertIn("--flag", cquerys[0])
        self.assertNotIn("--flag", cquerys[1])
        self.assertIn("--universe_scope=//:a,//:b", cquerys[1])


if __name__ == "__main__":
    unittest.main()
