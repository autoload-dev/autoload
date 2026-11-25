"""Decoding and batching of evaluated configured evidence."""

import unittest
from pathlib import Path
from unittest.mock import patch

from tools.ci.lanes import PROFILE
from tools.conventions.context import EvidenceError, Module
from tools.docs.evidence import EvaluatedBazel, behavior_tests, decode_configured

APP = '{"label":"@@//:app","files":1,"runfiles":2,"executable":true,"providers":["DefaultInfo"],"groups":["bundle"]}'
ACTUAL = '{"label":"@@//:app.macos","files":1,"runfiles":0,"executable":false,"providers":[],"groups":[]}'


class EvidenceTest(unittest.TestCase):
    def test_decodes_counts_and_names_by_unqualified_label(self) -> None:
        target = decode_configured(APP)[":app"]
        self.assertEqual((1, 2, True), (target.files, target.runfiles, target.executable))
        self.assertEqual(frozenset({"bundle"}), target.groups)
        with self.assertRaisesRegex(EvidenceError, "invalid evaluated configured"):
            decode_configured('{"label":"//:app"}')

    def test_a_label_in_two_configurations_is_an_error(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "more than one configuration"):
            decode_configured(APP + "\n" + APP)

    def test_aliases_are_configured_separately_under_their_own_label(self) -> None:
        module = Module(Path("."), ())
        bazel = EvaluatedBazel(Path("/workspace"))
        with patch(
            "tools.docs.evidence.run_tool", side_effect=[APP + "\n" + ACTUAL, ACTUAL]
        ) as run:
            observed = bazel.configured(module, ["//:app", "//:alias"])
        self.assertEqual(2, run.call_count)
        self.assertEqual("@@//:app", observed["//:app"].label)
        self.assertEqual("@@//:app.macos", observed["//:alias"].label)

    def test_behavior_tests_resolve_in_the_module_they_name(self) -> None:
        editor_view = (
            "//godot/private/tests/editor_view:editor_view_writes_edits_back_test"
        )
        engine = "//e2e/rules_godot/patched_engine/tests:app_runs_patched_engine_test"
        behavior = {
            "//godot:defs.bzl%godot_metadata_sync": [editor_view],
            "//godot/engine:repositories.bzl%godot_engine_build": [
                {"target": engine, "module": "."}
            ],
        }
        self.assertEqual(
            {"rules_godot": {editor_view}, ".": {engine}},
            behavior_tests(behavior),
        )
        bazel = EvaluatedBazel(Path("/workspace"))
        with patch("tools.docs.evidence.run_tool", return_value=engine) as run:
            found = bazel.tests([engine], Module(Path("tests"), ()))
        self.assertEqual({engine}, found)
        self.assertEqual(Path("/workspace/tests"), run.call_args.args[1])

    def test_only_configured_queries_run_in_the_lane_s_profile(self) -> None:
        bazel = EvaluatedBazel(Path("/workspace"), "android")
        module = Module(Path("."), ())
        with patch("tools.docs.evidence.run_tool", return_value=APP) as run:
            bazel.configured(module, ["//:app"], ["--config=android"])
            bazel.tests(["//:app"], module)
        configured, tests = (call.args for call in run.call_args_list)
        self.assertEqual({PROFILE: "android"}, configured[2])
        self.assertEqual({}, tests[2])
        self.assertEqual(Path("/workspace"), configured[1])


if __name__ == "__main__":
    unittest.main()
