"""Index a project's missing metadata once and check packs against it."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import metadata_index

_SCENE = """[gd_scene format=3]

[ext_resource type="Script" path="res://main.gd" id="1"]
[ext_resource type="Texture2D" path="res://icon.png" id="2"]

[node name="Main" type="Node"]
"""


class MetadataIndexTest(unittest.TestCase):
    def index(self, base: Path) -> dict:
        (base / "main.tscn").write_text(_SCENE)
        (base / "main.gd.uid").write_text("uid://main\n")
        # The icon's UID exists only in an import result.
        tree = base / "imports"
        tree.mkdir()
        (tree / "icon.png.import").write_text('[remap]\n\nuid="uid://icon"\n')
        (base / "manifest.json").write_text(
            json.dumps(
                {
                    "files": {
                        "main.tscn": str(base / "main.tscn"),
                        "main.gd.uid": str(base / "main.gd.uid"),
                    },
                    "members": ["main.tscn", "main.gd", "main.gd.uid", "icon.png"],
                }
            )
        )
        output = base / "index.json"
        argv = [
            "index",
            "index",
            "--manifest",
            str(base / "manifest.json"),
            "--output",
            str(output),
            "--import",
            str(tree),
        ]
        with mock.patch("sys.argv", argv):
            metadata_index.main()
        return json.loads(output.read_text())

    def test_index_covers_members_and_generated_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            index = self.index(Path(temp))
        self.assertEqual(
            {"main.gd": "uid://main", "icon.png": "uid://icon"}, index["uids"]
        )
        self.assertEqual({"main.tscn": {"issues": ["Main"]}}, index["node_ids"])
        self.assertEqual(
            {
                "main.tscn": {
                    "issues": ["res://main.gd (missing)", "res://icon.png (missing)"],
                    "uids": {"main.gd": "uid://main", "icon.png": "uid://icon"},
                }
            },
            index["resource_uids"],
        )

    def test_check_fails_for_the_packs_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            self.index(base)
            for kind, checked, named in [
                ("node_ids", ["main.tscn"], "res://main.tscn: Main"),
                ("resource_uids", ["main.tscn"], "res://main.gd (missing)"),
                ("resource_uids", [], None),
            ]:
                manifest = base / f"check-{kind}-{len(checked)}.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "kind": kind,
                            "pack": "//game:pack",
                            "project": "//game:project",
                            "index": str(base / "index.json"),
                            "checked": checked,
                        }
                    )
                )
                argv = [
                    "index",
                    "check",
                    "--manifest",
                    str(manifest),
                    "--output",
                    str(base / "ok"),
                ]
                with (
                    self.subTest(kind=kind, checked=checked),
                    mock.patch("sys.argv", argv),
                ):
                    if named is None:
                        metadata_index.main()
                        continue
                    with self.assertRaises(SystemExit) as failure:
                        metadata_index.main()
                    self.assertIn(named, str(failure.exception))
                    self.assertIn(
                        "//godot/metadata:" + kind + "=assign", str(failure.exception)
                    )


if __name__ == "__main__":
    unittest.main()
