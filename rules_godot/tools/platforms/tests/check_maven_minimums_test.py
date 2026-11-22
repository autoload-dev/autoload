"""The minimum check of an Android application's Maven modules against Godot's graph."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from tools.platforms import check_maven_minimums

GRAPH = {
    "artifacts": {
        "androidx.core:core:aar": {"version": "1.8.0"},
        "androidx.lifecycle:lifecycle-common": {"version": "2.6.1"},
        "com.google.guava:listenablefuture": {"version": "1.0"},
    },
}


class VersionOrderTest(unittest.TestCase):
    def assertOrdered(self, lower: str, higher: str) -> None:
        self.assertLess(check_maven_minimums.compare_versions(lower, higher), 0)
        self.assertGreater(check_maven_minimums.compare_versions(higher, lower), 0)

    def test_numeric_segments_compare_numerically(self) -> None:
        self.assertOrdered("2.6.1", "2.10.0")
        self.assertOrdered("1.7.0", "1.8.0")
        self.assertEqual(check_maven_minimums.compare_versions("1.0", "1.0.0"), 0)

    def test_qualifiers_follow_maven_order(self) -> None:
        self.assertOrdered("1.0-alpha01", "1.0-beta02")
        self.assertOrdered("1.0-beta02", "1.0-rc01")
        self.assertOrdered("1.0-rc01", "1.0-SNAPSHOT")
        self.assertOrdered("1.0-SNAPSHOT", "1.0")
        self.assertOrdered("1.0", "1.0-sp")
        self.assertOrdered("1.0-sp", "1.0-vendor")
        self.assertEqual(check_maven_minimums.compare_versions("1.0-final", "1.0"), 0)
        self.assertEqual(check_maven_minimums.compare_versions("1.0-cr1", "1.0-rc1"), 0)

    def test_qualified_version_above_older_release(self) -> None:
        self.assertOrdered("1.8.0", "1.9.0-rc01")

    def test_guava_placeholder_is_highest(self) -> None:
        self.assertOrdered("1.0", "9999.0-empty-to-avoid-conflict-with-guava")


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.graph = self.root / "maven_graph_install.json"
        self.graph.write_text(json.dumps(GRAPH))
        self.source = self.root / "GodotApp.java"
        self.source.write_bytes(b"package com.godot.game;\nclass GodotApp {}\n")
        self.output = self.root / "out" / "GodotApp.java"
        self.output.parent.mkdir()

    def check(self, *coordinates: str) -> tuple[int, str]:
        listing = self.root / "coordinates.txt"
        listing.write_text("".join(line + "\n" for line in coordinates))
        argv = [
            "check",
            "--coordinates",
            str(listing),
            "--graph",
            str(self.graph),
            "--source",
            str(self.source),
            "--output",
            str(self.output),
            "--application",
            "//game:app",
            "--engine-minor",
            "4.7",
        ]
        stderr = io.StringIO()
        with mock.patch("sys.argv", argv), redirect_stderr(stderr):
            status = check_maven_minimums.main()
        return status, stderr.getvalue()

    def test_met_minimums_copy_the_source_unchanged(self) -> None:
        status, message = self.check(
            "androidx.core:core:1.9.0-rc01",
            "androidx.lifecycle:lifecycle-common:2.6.1",
        )
        self.assertEqual((status, message), (0, ""))
        self.assertEqual(self.output.read_bytes(), self.source.read_bytes())

    def test_modules_absent_from_one_side_are_ignored(self) -> None:
        # The application lacks lifecycle; Godot's graph lacks appauth.
        status, _ = self.check(
            "androidx.core:core:1.8.0",
            "net.openid:appauth:0.0.1",
        )
        self.assertEqual(status, 0)

    def test_a_module_at_several_versions_counts_at_its_lowest(self) -> None:
        status, message = self.check(
            "androidx.core:core:1.9.0",
            "androidx.core:core:1.7.0",
            "androidx.core:core:1.8.0",
        )
        self.assertEqual(status, 1)
        self.assertIn("resolved 1.7.0  minimum 1.8.0", message)

    def test_shortfalls_fail_with_the_diagnostic_and_no_output(self) -> None:
        status, message = self.check(
            "com.google.guava:listenablefuture:1.0",
            "androidx.lifecycle:lifecycle-common:2.2.0",
            "androidx.core:core:1.7.0",
        )
        self.assertEqual(status, 1)
        self.assertFalse(self.output.exists())
        self.assertEqual(
            message.splitlines()[:4],
            [
                (
                    "//game:app: the shared Maven installation resolves modules "
                    "below Godot 4.7's minimums."
                ),
                (
                    "Godot's template activity and Android shell library need, as "
                    "Godot's Gradle export resolves them:"
                ),
                "  androidx.core:core                   resolved 1.7.0  minimum 1.8.0",
                "  androidx.lifecycle:lifecycle-common  resolved 2.2.0  minimum 2.6.1",
            ],
        )
        self.assertIn("REPIN=1 bazel run @maven//:pin", message)


if __name__ == "__main__":
    unittest.main()
