"""The graph action over generated source declarations infers declared edges."""

import json
import sys
import unittest
from pathlib import Path


class ResourceGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    def test_graph_is_complete_without_diagnostics(self) -> None:
        self.assertEqual([], self.graph["diagnostics"])
        self.assertTrue(self.graph["complete"])

    def test_graph_has_each_declared_source_and_the_project_file(self) -> None:
        self.assertEqual(
            [
                "res://main/content.tres",
                "res://main/main.gd",
                "res://main/main.tscn",
                "res://project.godot",
            ],
            [node["path"] for node in self.graph["nodes"]],
        )

    def test_graph_infers_the_project_edges(self) -> None:
        inferred = {
            (edge["source"], edge["target"])
            for edge in self.graph["edges"]
            if edge["origin"] == "inferred"
        }
        self.assertEqual(
            {
                ("res://main/main.gd", "res://main/content.tres"),
                ("res://main/main.tscn", "res://main/main.gd"),
                ("res://project.godot", "res://main/main.tscn"),
            },
            inferred,
        )

    def test_edges_of_declared_sources_are_declared(self) -> None:
        self.assertTrue(
            all(
                edge["declared"]
                for edge in self.graph["edges"]
                if edge["source"] != "res://project.godot"
            )
        )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
