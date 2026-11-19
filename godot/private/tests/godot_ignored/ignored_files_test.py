"""
Check that a pack leaves out what Godot ignores, that the graph marks it Godot-ignored and
that a pack's selection warns about an unacknowledged read of it.
"""

import json
import sys
import unittest
from pathlib import Path

from tools.pck import pck_file_contents, pck_file_member

PACK, GRAPH, SELECTION, UNACKNOWLEDGED = (Path(path) for path in sys.argv[1:5])
sys.argv = sys.argv[:1]


class IgnoredFilesTest(unittest.TestCase):
    def test_pack_holds_no_ignored_directory_and_no_ignored_class(self) -> None:
        paths = pck_file_contents(PACK, include_paths=True)["paths"]
        self.assertIn("main/reader.gd.uid", paths)
        self.assertEqual(
            [path for path in paths if path.startswith(("report/", "demo/"))], []
        )
        # Godot's include filter packs a hidden file of a visible directory.
        self.assertIn("main/.notes.txt", paths)
        classes = pck_file_member(PACK, ".godot/global_script_class_cache.cfg")
        self.assertNotIn(b"IgnoredHelper", classes)
        self.assertNotIn(b"DemoHelper", classes)

    def test_graph_marks_ignored_files_without_warnings(self) -> None:
        graph = json.loads(GRAPH.read_text())
        ignored = sorted(
            node["path"] for node in graph["nodes"] if node["analysis"] == "ignored"
        )
        self.assertEqual(
            ignored,
            [
                "res://demo/demo.gd",
                "res://demo/project.godot",
                "res://main/.notes.txt",
                "res://report/.gdignore",
                "res://report/helper.gd",
                "res://report/logo.png",
                "res://report/template.html",
            ],
        )
        self.assertEqual(graph["coverage"]["ignored"], ignored)
        self.assertEqual(
            [item for item in graph["diagnostics"] if item["path"] in ignored], []
        )

    def test_selection_warns_about_unacknowledged_reads_of_ignored_files(self) -> None:
        self.assertEqual(json.loads(SELECTION.read_text())["diagnostics"], [])
        [warning] = json.loads(UNACKNOWLEDGED.read_text())["diagnostics"]
        self.assertEqual(
            (warning["code"], warning["path"], warning["line"], warning["severity"]),
            ("ignored_reference", "res://unacknowledged/reader.gd", 7, "warning"),
        )
        self.assertIn(
            "res://report/template.html, which Godot's export leaves out: "
            "res://report/.gdignore hides its directory",
            warning["message"],
        )


if __name__ == "__main__":
    unittest.main()
