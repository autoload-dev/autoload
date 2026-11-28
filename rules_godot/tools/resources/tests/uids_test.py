"""Point each ext_resource at the UID of the file it names."""

import tempfile
import unittest
from pathlib import Path

from tools.resources.uids import (
    id_to_uid,
    known_uids,
    reference_updates,
    uid_sources,
    uid_to_id,
    with_resource_uids,
)

_SCENE = """[gd_scene format=3]

[ext_resource type="Script" path="res://main.gd" id="1"]
[ext_resource type="Texture2D" uid="uid://stale" path="res://icon.png" id="2"]
[ext_resource type="PackedScene" uid="uid://level" path="res://level.tscn" id="3"]
[ext_resource type="Script" path="res://unknown.gd" id="4"]

[node name="Main" type="Node" unique_id=1]
"""

_UIDS = {
    "main.gd": "uid://main",
    "icon.png": "uid://icon",
    "level.tscn": "uid://level",
}


class ResourceUidTest(unittest.TestCase):
    def test_ids_and_their_uid_texts_round_trip(self) -> None:
        for value in (0, 24, 25, 33, 34, 2**63 - 1):
            with self.subTest(value=value):
                self.assertEqual(uid_to_id(id_to_uid(value)), value)
        # A UID the Godot editor wrote.
        self.assertEqual(
            id_to_uid(uid_to_id("uid://c4fbx2ahn1kqw")), "uid://c4fbx2ahn1kqw"
        )

    def test_uids_come_from_sidecars_imports_and_resource_headers(self) -> None:
        self.assertEqual(
            {
                "main.gd": "uid://main",
                "icon.png": "uid://icon",
                "level.tscn": "uid://level",
                "theme.tres": "uid://theme",
            },
            known_uids(
                {
                    "main.gd.uid": "uid://main\n",
                    "icon.png.import": '[remap]\n\nimporter="texture"\nuid="uid://icon"\n',
                    "level.tscn": '[gd_scene format=3 uid="uid://level"]\n',
                    "theme.tres": '[gd_resource type="Theme" format=3 uid="uid://theme"]\n',
                    "plain.tscn": "[gd_scene format=3]\n",
                    "main.gd": "extends Node\n",
                    "orphan.gd.uid": "uid://orphan\n",
                },
                # A sidecar identifies only a declared file.
                {"main.gd", "icon.png", "level.tscn", "theme.tres", "plain.tscn"},
            ),
        )

    def test_uid_sources_are_sidecars_and_text_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            files = {}
            for path in ["main.gd", "main.gd.uid", "icon.png.import", "level.tscn"]:
                files[path] = Path(temp) / path.replace("/", "_")
                files[path].write_text(path)
            self.assertEqual(
                {path: path for path in ["main.gd.uid", "icon.png.import", "level.tscn"]},
                uid_sources(files),
            )

    def test_missing_and_stale_uids_are_set_where_godot_writes_them(self) -> None:
        updated = with_resource_uids(_SCENE, "main.tscn", _UIDS)
        self.assertIn(
            '[ext_resource type="Script" uid="uid://main" path="res://main.gd" id="1"]',
            updated,
        )
        self.assertIn(
            '[ext_resource type="Texture2D" uid="uid://icon" path="res://icon.png" id="2"]',
            updated,
        )
        self.assertEqual(
            _SCENE.splitlines()[4:],
            updated.splitlines()[4:],
            "correct and unknown references stay as they are",
        )

    def test_updates_name_missing_and_stale_references_with_their_uids(self) -> None:
        self.assertEqual(
            (
                ["res://main.gd (missing)", "res://icon.png (stale)"],
                {"main.gd": "uid://main", "icon.png": "uid://icon"},
            ),
            reference_updates(_SCENE, "main.tscn", _UIDS),
        )
        completed = with_resource_uids(_SCENE, "main.tscn", _UIDS)
        self.assertEqual(([], {}), reference_updates(completed, "main.tscn", _UIDS))

    def test_relative_paths_resolve_against_the_scene(self) -> None:
        scene = '[ext_resource type="Script" path="../main.gd" id="1"]\n'
        self.assertEqual(
            '[ext_resource type="Script" uid="uid://main" path="../main.gd" id="1"]\n',
            with_resource_uids(scene, "levels/one.tscn", _UIDS),
        )

    def test_references_without_a_path_in_the_project_stay(self) -> None:
        scene = (
            '[ext_resource type="Script" uid="uid://main" id="1"]\n'
            '[ext_resource type="Script" path="../../main.gd" id="2"]\n'
        )
        self.assertEqual(scene, with_resource_uids(scene, "levels/one.tscn", _UIDS))

    def test_a_reference_without_type_gets_its_uid_first(self) -> None:
        self.assertEqual(
            '[ext_resource uid="uid://main" path="res://main.gd" id="1"]\n',
            with_resource_uids(
                '[ext_resource path="res://main.gd" id="1"]\n', "main.tscn", _UIDS
            ),
        )

    def test_line_endings_are_kept(self) -> None:
        scene = _SCENE.replace("\n", "\r\n")
        self.assertEqual(
            with_resource_uids(_SCENE, "main.tscn", _UIDS).replace("\n", "\r\n"),
            with_resource_uids(scene, "main.tscn", _UIDS),
        )


if __name__ == "__main__":
    unittest.main()
