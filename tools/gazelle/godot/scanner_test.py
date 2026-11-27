"""The scanner of Gazelle's Godot language, by its scans and its protocol."""

import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.gazelle.godot.scanner import scan, serve


class ScanTest(unittest.TestCase):
    def test_a_script_references_paths_uids_and_names_at_load_time(self) -> None:
        script = (
            "class_name Courier\n"
            'extends "res://main/shared/body.gd"\n'
            'const Sound := preload("uid://sound")\n'
            'var data := FileAccess.get_file_as_string("res://tests/data.json")\n'
            "var level: LevelDefinition\n"
        )
        found = scan("res://main/courier.gd", script)
        self.assertEqual(found["classes"], ["Courier"])
        self.assertIn(
            {"kind": "res", "value": "res://main/shared/body.gd"}, found["refs"]
        )
        self.assertIn({"kind": "uid", "value": "uid://sound"}, found["refs"])
        self.assertIn({"kind": "class", "value": "LevelDefinition"}, found["refs"])
        self.assertNotIn({"kind": "res", "value": "res://tests/data.json"}, found["refs"])
        self.assertEqual(found["runtime"], ["res://tests/data.json"])

    def test_a_suite_extends_its_framework_by_name(self) -> None:
        found = scan("res://tests/RouteTest.gd", "extends GdUnitTestSuite\n")
        self.assertEqual(found["extends"], "GdUnitTestSuite")

    def test_a_gltf_names_its_importer_inputs_as_members(self) -> None:
        found = scan("res://models/ship.gltf", '{"buffers": [{"uri": "ship.bin"}]}')
        self.assertEqual(found["members"], ["res://models/ship.bin"])
        self.assertEqual(found["refs"], [])

    def test_an_extension_source_registers_classes(self) -> None:
        source = (
            "godot::ClassDB::register_class<NativeCounter>();\n"
            "ClassDB::register_abstract_class< Shape >();\n"
            "GDREGISTER_RUNTIME_CLASS(Field);\n"
        )
        self.assertEqual(
            scan("res://native/counter.cc", source)["classes"],
            ["Field", "NativeCounter", "Shape"],
        )

    def test_other_formats_scan_empty(self) -> None:
        self.assertEqual(scan("res://notes.txt", 'load("res://x.gd")')["refs"], [])


class ServeTest(unittest.TestCase):
    def test_each_request_line_gets_one_answer_line_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            uid = Path(directory, "game.gd.uid")
            uid.write_text("uid://game\n", encoding="utf-8")
            image = Path(directory, "sky.png")
            image.write_bytes(b"\x89PNG")
            request = {
                "files": [
                    {"file": str(uid), "path": "res://game.gd.uid"},
                    {"file": str(image), "path": "res://sky.png"},
                    {
                        "file": str(Path(directory, "missing.gd")),
                        "path": "res://missing.gd",
                    },
                ]
            }
            answers = io.StringIO()
            serve(
                io.StringIO(
                    json.dumps(request) + "\n" + json.dumps({"files": []}) + "\n"
                ),
                answers,
            )
        lines = answers.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        files = json.loads(lines[0])["files"]
        self.assertEqual([item["uids"] for item in files], [["uid://game"], [], []])
        self.assertEqual(json.loads(lines[1]), {"files": []})


if __name__ == "__main__":
    unittest.main()
