"""Decoding and batching of evaluated configured evidence."""

import unittest
from pathlib import Path
from unittest.mock import patch

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
        engine = "//patched_engine/tests:app_runs_patched_engine_test"
        behavior = {
            "//godot:defs.bzl%godot_metadata_sync": [editor_view],
            "//godot/engine:repositories.bzl%godot_engine_build": [
                {"target": engine, "module": "tests"}
            ],
        }
        self.assertEqual(
            {".": {editor_view}, "tests": {engine}},
            behavior_tests(behavior),
        )
        bazel = EvaluatedBazel(Path("/workspace"))
        with patch("tools.docs.evidence.run_tool", return_value=engine) as run:
            found = bazel.tests([engine], Module(Path("tests"), ()))
        self.assertEqual({engine}, found)
        self.assertEqual(Path("/workspace/tests"), run.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
