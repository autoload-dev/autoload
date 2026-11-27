"""What the scanner reads in one file on its own, as Gazelle's Godot language uses it."""

import unittest

from tools.resource_graph import file_references


class FileReferencesTest(unittest.TestCase):
    """What one file declares and references on its own, as Gazelle's Godot language reads it."""

    def test_a_script_declares_its_class_and_names_what_it_references(self) -> None:
        script = (
            "class_name Courier\n"
            "extends Body\n"
            'const Palette := preload("../shared/palette.tres")\n'
            'var data := FileAccess.get_file_as_string("res://tests/data.json")\n'
            'var scene = load("main/run.tscn")\n'
            "func _ready() -> void:\n"
            "\tRouteModel.new()\n"
            "\tself.Ignored = 1\n"
        )
        found = file_references("res://main/courier/courier.gd", script)
        self.assertEqual(found["classes"], ["Courier"])
        self.assertEqual(found["extends"], "Body")
        self.assertEqual(found["uids"], [])
        self.assertTrue({"Body", "RouteModel", "FileAccess"} <= set(found["names"]))
        self.assertFalse({"Courier", "Ignored"} & set(found["names"]))
        self.assertEqual(
            found["references"],
            [
                {"kind": "file_access", "path": "res://tests/data.json", "uid": None},
                {"kind": "load", "path": "res://main/run.tscn", "uid": None},
                {
                    "kind": "preload",
                    "path": "res://main/shared/palette.tres",
                    "uid": None,
                },
            ],
        )

    def test_a_scene_authors_its_uid_and_references_by_path_and_uid(self) -> None:
        scene = (
            '[gd_scene format=3 uid="uid://scene"]\n\n'
            '[ext_resource type="Script" uid="uid://script" path="res://main/game.gd" id="1"]\n'
            '[ext_resource type="Texture2D" uid="uid://sky" id="2"]\n'
        )
        found = file_references("res://main/game.tscn", scene)
        self.assertEqual(found["uids"], ["uid://scene"])
        self.assertEqual(found["extends"], None)
        self.assertEqual(
            found["references"],
            [
                {"kind": "resource", "path": None, "uid": "uid://sky"},
                {"kind": "resource", "path": "res://main/game.gd", "uid": "uid://script"},
            ],
        )

    def test_sidecars_author_the_uid_of_their_file(self) -> None:
        self.assertEqual(
            file_references("res://main/game.gd.uid", "uid://script\n")["uids"],
            ["uid://script"],
        )
        imported = '[remap]\n\nimporter="texture"\nuid="uid://sky"\n'
        self.assertEqual(
            file_references("res://main/sky.png.import", imported)["uids"], ["uid://sky"]
        )

    def test_a_gltf_names_the_files_its_importer_reads(self) -> None:
        model = (
            '{"buffers": [{"uri": "ship.bin"}], "images": [{"uri": "hull%20paint.png"}]}'
        )
        found = file_references("res://models/ship.gltf", model)
        self.assertEqual(
            [(item["kind"], item["path"]) for item in found["references"]],
            [
                ("gltf_buffers", "res://models/ship.bin"),
                ("gltf_images", "res://models/hull paint.png"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
