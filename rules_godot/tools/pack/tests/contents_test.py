import json
import tempfile
import unittest
from pathlib import Path

from tools.godot_export import export_presets
from tools.pack.contents import content_selection, inspect_export


class PackContentsTest(unittest.TestCase):
    def test_exports_exclude_every_staged_path_outside_the_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "content.json").write_text(
                json.dumps({"pack": "//:base", "resources": {"main.gd": "a"}})
            )
            manifest = {
                "content": "content.json",
                "member_resource_paths": {"main.gd": "a", "dlc/level.gd": "b"},
                "import_resource_paths": {"model.bin": "c"},
            }
            self.assertEqual(
                ({"main.gd"}, {"dlc/level.gd", "model.bin"}),
                content_selection(manifest, base),
            )
        with self.assertRaisesRegex(ValueError, "literal export filter"):
            export_presets({"preset_platform": "Linux"}, ["levels/[1].json"])

    def test_generated_uid_of_an_excluded_script_is_a_leak(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError, "excluded resources in the PCK: dlc.gd.uid"
        ):
            inspect_export(
                {
                    "paths": ["res://main.gd", "res://dlc.gd.uid"],
                    "file_count": 2,
                },
                {"main.gd"},
                {"dlc.gd"},
            )
        report = inspect_export(
            {"paths": ["res://main.gd", "res://main.gd.uid"], "file_count": 2},
            {"main.gd"},
            {"dlc.gd"},
        )
        self.assertEqual(["main.gd"], report["selected_paths"])

    def test_declared_sidecars_are_never_missing_and_have_no_sidecars(self) -> None:
        # Godot writes no sidecar beside a sidecar, and packs sidecars as its own
        # UID and import tables, never as resources.
        report = inspect_export(
            {"paths": ["res://main.gd", "res://dlc.gd.uid.uid"], "file_count": 2},
            {"main.gd", "main.gd.uid", "icon.png.import"},
            {"dlc.gd.uid"},
        )
        self.assertEqual(
            ["icon.png.import", "main.gd", "main.gd.uid"], report["selected_paths"]
        )

    def test_files_godot_ignores_are_never_missing(self) -> None:
        # Godot exports nothing below a directory that holds a .gdignore.
        report = inspect_export(
            {"paths": ["res://main.gd"], "file_count": 1},
            {"main.gd", "template/.gdignore", "template/css/style.css"},
            set(),
            {"template/.gdignore", "template/css/style.css"},
        )
        self.assertEqual(
            ["main.gd", "template/.gdignore", "template/css/style.css"],
            report["selected_paths"],
        )
        with self.assertRaisesRegex(
            RuntimeError, "omitted declared resources.*style.css"
        ):
            inspect_export(
                {"paths": ["res://main.gd"], "file_count": 1},
                {"main.gd", "template/css/style.css"},
                set(),
            )


if __name__ == "__main__":
    unittest.main()
