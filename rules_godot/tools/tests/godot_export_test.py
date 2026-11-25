import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import godot_export
from tools.godot_export import exclusive_export, export_lock, export_presets, validate_pck
from tools.node_ids import with_node_ids
from tools.tests.empty_pck import pck_bytes, write_pck


class GodotExportTest(unittest.TestCase):
    def setUp(self) -> None:
        # On macOS every export of the user, other builds' included, takes the same lock,
        # so a test that took it would wait for them. Each test locks a file of its own.
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.export_lock = Path(temp) / "export.lock"
        self.enterContext(
            mock.patch.object(godot_export, "export_lock", return_value=self.export_lock)
        )

    def test_export_preset_escapes_strings(self) -> None:
        preset = export_presets({"preset_platform": "Android", "features": ['a"b']})
        self.assertIn('platform="Android"', preset)
        self.assertIn(r"a\"b", preset)

    def test_export_selection_is_explicit_and_raw_files_are_included(self) -> None:
        preset = export_presets(
            {"preset_platform": "Linux", "preset_settings": {"script_export_mode": "2"}},
            ["native/b.so", "native/a.so"],
        )
        self.assertIn('include_filter="*"', preset)
        # Godot writes .uid files beside scripts; they leave with their source.
        self.assertIn(
            'exclude_filter="native/a.so,native/a.so.uid,native/b.so,native/b.so.uid"',
            preset,
        )
        self.assertIn("script_export_mode=2", preset)

    def test_export_options_follow_the_managed_ones(self) -> None:
        preset = export_presets(
            {
                "preset_platform": "Android",
                "preset_prelude": {"binary_format/architecture": '"arm64"'},
                "export_options": {
                    "texture_format/etc2_astc": "true",
                    "package/name": '"Demo"',
                },
            }
        )
        options = preset.split("[preset.0.options]\n", 1)[1].splitlines()
        self.assertEqual(
            [
                'binary_format/architecture="arm64"',
                'package/name="Demo"',
                "texture_format/etc2_astc=true",
            ],
            [line for line in options if line],
        )
        with self.assertRaises(ValueError):
            export_presets(
                {
                    "preset_platform": "Linux",
                    "export_options": {"x/y": 'load("res://a.gd")'},
                }
            )

    def test_prelude_is_sorted_before_authored_duplicates(self) -> None:
        preset = export_presets(
            {
                "preset_platform": "macOS",
                "preset_prelude": {
                    "binary_format/embed_pck": "false",
                    "binary_format/architecture": '"arm64"',
                },
                "export_options": {"binary_format/embed_pck": "true"},
            }
        )
        options = preset.split("[preset.0.options]\n", 1)[1].strip().splitlines()
        self.assertEqual(
            [
                'binary_format/architecture="arm64"',
                "binary_format/embed_pck=false",
                "binary_format/embed_pck=true",
            ],
            options,
        )

    def test_absent_prelude_has_no_platform_fallback(self) -> None:
        for prelude in [{}, {"preset_prelude": {}}]:
            self.assertNotIn(
                "binary_format/", export_presets({"preset_platform": "macOS", **prelude})
            )

    def test_prelude_literals_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            export_presets(
                {
                    "preset_platform": "macOS",
                    "preset_prelude": {"x/y": 'load("res://a.gd")'},
                }
            )

    @unittest.skipUnless(sys.platform == "darwin", "macOS shares tmpproject.binary")
    def test_exports_lock_the_user_temporary_directory(self) -> None:
        # export_lock, imported by name, is the real function; setUp patches the module's.
        if export_lock() is None:
            self.fail("macOS exports must share a lock")
        with exclusive_export():
            self.assertTrue(self.export_lock.exists())

    def test_pack_exports_scenes_with_stable_node_ids(self) -> None:
        scene = '[gd_scene format=3]\n\n[node name="Main" type="Node"]\n'
        for assign, expected in [
            (True, with_node_ids(scene, "main.tscn")),
            (False, scene),
        ]:
            with self.subTest(assign=assign), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                (base / "project.godot").write_text("config_version=5\n")
                (base / "main.tscn").write_text(scene)
                (base / "content.json").write_text(
                    json.dumps({"resources": {"main.tscn": "main.tscn"}})
                )
                (base / "index.json").write_text(
                    json.dumps({"node_ids": {"main.tscn": {"issues": ["Main"]}}})
                )
                exported: list[str] = []

                def editor(
                    manifest: dict,
                    execroot: Path,
                    root: Path,
                    work: Path,
                    args: list[str],
                    exported: list[str] = exported,
                ) -> dict:
                    if "--export-pack" in args:
                        exported.append((root / "main.tscn").read_text())
                        write_pck(Path(args[-1]))
                    return {}

                manifest = {
                    "project_file": "project.godot",
                    "content": "content.json",
                    "member_resource_paths": {"main.tscn": "main.tscn"},
                    "editor": "editor",
                    "version": "4.7.2",
                    "preset_platform": "Linux",
                    "variant": "release",
                    "owner": "//game:pack",
                    "metadata_index": {
                        "path": "index.json",
                        "assign": ["node_ids"] if assign else [],
                    },
                }
                with (
                    mock.patch.object(godot_export, "run_action", editor),
                    mock.patch.object(godot_export, "export_presets", return_value=""),
                    mock.patch.object(godot_export, "write_report"),
                ):
                    godot_export.pack(manifest, base / "out.pck", base / "r.json", base)
                self.assertEqual([expected], exported)
                self.assertEqual(scene, (base / "main.tscn").read_text())

    def test_pack_starts_the_editor_once_for_its_export(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            (base / "content.json").write_text(json.dumps({"resources": {}}))
            launches: list[list[str]] = []

            def editor(
                manifest: dict, execroot: Path, root: Path, work: Path, args: list[str]
            ) -> dict:
                launches.append(args)
                if "--export-pack" in args:
                    write_pck(Path(args[-1]))
                return {}

            manifest = {
                "project_file": "project.godot",
                "content": "content.json",
                "member_resource_paths": {},
                "editor": "editor",
                "version": "4.7.2",
                "preset_platform": "Linux",
                "variant": "release",
                "owner": "//game:pack",
            }
            with (
                mock.patch.object(godot_export, "run_action", editor),
                mock.patch.object(godot_export, "export_presets", return_value=""),
            ):
                godot_export.pack(manifest, base / "out.pck", base / "report.json", base)
            self.assertEqual(
                [["--export-pack", "Bazel", str(base / "out.pck")]], launches
            )

    def test_a_pack_fails_when_its_export_meets_an_unknown_class(self) -> None:
        # D28: exporting without the extension of a class drops its values from the
        # converted scenes and resources while the export still succeeds; Godot's only
        # report is this message, as printed by Godot 4.7.2 in that export.
        output = (
            "Godot Engine v4.7.2.stable.official.ed1daf0bf\n"
            "ERROR: Cannot get class 'ProbeNode'.\n"
            "   at: _instantiate_internal (core/object/class_db.cpp:587)\n"
            "ERROR: Cannot get class 'ProbeData'.\n"
            "   at: _instantiate_internal (core/object/class_db.cpp:587)\n"
            "[ DONE ] savepack\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            (base / "content.json").write_text(json.dumps({"resources": {}}))

            def editor(
                manifest: dict, execroot: Path, root: Path, work: Path, args: list[str]
            ) -> dict:
                write_pck(Path(args[-1]))
                return {"output": output}

            manifest = {
                "project_file": "project.godot",
                "content": "content.json",
                "member_resource_paths": {},
                "editor": "editor",
                "version": "4.7.2",
                "preset_platform": "Linux",
                "variant": "release",
                "owner": "//game:pack",
            }
            with (
                mock.patch.object(godot_export, "run_action", editor),
                mock.patch.object(godot_export, "export_presets", return_value=""),
                self.assertRaisesRegex(
                    RuntimeError,
                    "//game:pack: Godot did not know the class ProbeData, ProbeNode "
                    "during the export(.|\n)*a library for the platform that runs "
                    "the export",
                ),
            ):
                godot_export.pack(manifest, base / "out.pck", base / "report.json", base)

    def test_zero_exit_bogus_export_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pck = Path(temp) / "main.pck"
            pck.write_bytes(struct.pack("<II", 0, 2) + bytes(128))
            with self.assertRaisesRegex(RuntimeError, r"valid Godot 4\.7\.2\+ PCK v4"):
                validate_pck(pck)

    def test_only_modern_pack_format_and_engine_versions_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pck = Path(temp) / "main.pck"
            for version in (2, 3, 5):
                pck.write_bytes(pck_bytes(version=version, padding=128))
                with (
                    self.subTest(format=version),
                    self.assertRaisesRegex(RuntimeError, "PCK v4"),
                ):
                    validate_pck(pck)
            for engine in [(4, 5, 1), (4, 7, 1), (5, 0, 0)]:
                pck.write_bytes(pck_bytes(engine=engine, padding=128))
                with (
                    self.subTest(engine=engine),
                    self.assertRaisesRegex(RuntimeError, "PCK v4"),
                ):
                    validate_pck(pck)
            for engine in [(4, 7, 2), (4, 7, 10), (4, 8, 0)]:
                pck.write_bytes(pck_bytes(engine=engine, padding=128))
                self.assertEqual(0, validate_pck(pck)["file_count"])


if __name__ == "__main__":
    unittest.main()
