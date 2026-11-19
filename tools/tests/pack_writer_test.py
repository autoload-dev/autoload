import json
import struct
import tempfile
import unittest
from pathlib import Path

from tools.godot_files import hidden_by
from tools.pack_writer import exported_import, raw_path, write
from tools.pck import pck_file_contents, pck_files, write_pck
from tools.resource_uids import uid_cache, uid_to_id

_TEXTURE_IMPORT = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://vj5ano28uc3c"
path.s3tc="res://.godot/imported/sky.png-1.s3tc.ctex"
path.etc2="res://.godot/imported/sky.png-1.etc2.ctex"
metadata={
"imported_formats": ["s3tc_bptc", "etc2_astc"],
"vram_texture": true
}

[deps]

source_file="res://sky.png"
dest_files=["res://.godot/imported/sky.png-1.s3tc.ctex", "res://.godot/imported/sky.png-1.etc2.ctex"]

[params]

compress/mode=2
"""


class ExportedImportTest(unittest.TestCase):
    def test_keeps_the_remap_section_of_the_exports_features(self) -> None:
        text, imported = exported_import(_TEXTURE_IMPORT, {"etc2", "android"})
        self.assertEqual(imported, [".godot/imported/sky.png-1.etc2.ctex"])
        self.assertNotIn("path.s3tc", text)
        self.assertIn('path.etc2="res://.godot/imported/sky.png-1.etc2.ctex"', text)
        self.assertIn('"vram_texture": true\n}\n', text)
        self.assertNotIn("[deps]", text)
        self.assertNotIn("[params]", text)

    def test_keeps_an_unconditional_path(self) -> None:
        text, imported = exported_import(
            '[remap]\n\nimporter="font_data_dynamic"\npath="res://.godot/imported/f.fontdata"\n\n[deps]\n\nx=1\n',
            set(),
        )
        self.assertEqual(imported, [".godot/imported/f.fontdata"])
        self.assertEqual(
            text,
            '[remap]\n\nimporter="font_data_dynamic"\npath="res://.godot/imported/f.fontdata"\n',
        )

    def test_rejects_an_import_without_remap(self) -> None:
        with self.assertRaises(ValueError):
            exported_import("[deps]\n\nx=1\n", set())


class IncludeFilterTest(unittest.TestCase):
    def test_packs_a_hidden_file_of_a_visible_directory_only(self) -> None:
        paths = {"main/.notes.txt", "report/.gdignore", "report/a.gd", ".hidden/b.gd"}
        self.assertIsNone(hidden_by("main/.notes.txt", paths))
        self.assertEqual("report/.gdignore", hidden_by("report/a.gd", paths))
        self.assertEqual(".hidden", hidden_by(".hidden/b.gd", paths))


class UidTest(unittest.TestCase):
    def test_reads_uids_as_godot_does(self) -> None:
        # The ID Godot 4.7.2 wrote into the export's UID cache for this UID; its
        # digits count from 'a' to 'z', then from '0' on as 'z' again.
        self.assertEqual(uid_to_id("uid://b73qwse0wrl46"), 4691277969339469357)

    def test_cache_lists_paths_with_their_ids(self) -> None:
        data = uid_cache({"main/game.gd": "uid://b73qwse0wrl46"})
        count, uid, length = struct.unpack_from("<IQI", data)
        self.assertEqual((count, uid), (1, 4691277969339469357))
        self.assertEqual(data[16 : 16 + length], b"res://main/game.gd")

    def test_cache_leaves_out_texts_that_are_no_uid(self) -> None:
        self.assertEqual(uid_cache({"a.gd": "uid://<invalid>"}), struct.pack("<I", 0))

    def test_raw_paths_resolve_uids(self) -> None:
        uids = {"icon.svg": "uid://b73qwse0wrl46"}
        self.assertEqual(raw_path("uid://b73qwse0wrl46", uids), "icon.svg")
        self.assertEqual(raw_path("res://splash.png", uids), "splash.png")
        self.assertEqual(raw_path("uid://vj5ano28uc3c", uids), "")


class WriteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def file(self, path: str, content: str | bytes) -> str:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            target.write_text(content, encoding="utf-8")
        else:
            target.write_bytes(content)
        return path

    def pack(self, facts: dict, members: dict[str, str | bytes]) -> dict[str, bytes]:
        member_paths = {
            path: self.file("src/" + path, content) for path, content in members.items()
        }
        self.file("import/sky.png.import", _TEXTURE_IMPORT)
        self.file("import/.godot/imported/sky.png-1.s3tc.ctex", b"s3tc")
        self.file("import/.godot/imported/sky.png-1.etc2.ctex", b"etc2")
        content = self.file("content.json", json.dumps({"resources": dict(member_paths)}))
        write_pck(
            self.root / "configuration.pck",
            {"project.binary": b"ECFG\0\0\0\0", "icudt_godot.dat": b"icu"},
            (4, 7, 2),
        )
        self.file("facts.json", json.dumps(facts))
        manifest = {
            "content": content,
            "member_resource_paths": member_paths,
            "configuration": "configuration.pck",
            "configuration_facts": "facts.json",
            "imports": ["import"],
            "version": "4.7.2",
            "preset_platform": "Android",
            "variant": "release",
            "owner": "//:pack",
        }
        output = self.root / "out.pck"
        write(manifest, output, self.root / "report.json", self.root)
        self.report = json.loads((self.root / "report.json").read_text())
        return pck_files(output)

    def test_packs_files_as_they_are_with_godots_caches(self) -> None:
        files = self.pack(
            {"features": ["etc2", "android"], "icon": "uid://vj5ano28uc3c"},
            {
                "main.tscn": '[gd_scene format=3 uid="uid://b73qwse0wrl46"]\n\n[node name="Main" type="Node"]\n',
                "player.gd": "class_name Player\nextends Node\n",
                "player.gd.uid": "uid://c1od550e86gw1\n",
                "sky.png": b"png",
                "native/native.gdextension": "[configuration]\n",
            },
        )
        self.assertEqual(
            sorted(files),
            [
                ".godot/extension_list.cfg",
                ".godot/global_script_class_cache.cfg",
                ".godot/imported/sky.png-1.etc2.ctex",
                ".godot/uid_cache.bin",
                "icudt_godot.dat",
                "main.tscn",
                "native/native.gdextension",
                "player.gd",
                "player.gd.uid",
                "project.binary",
                # The runtime reads the icon as an image file, besides its import.
                "sky.png",
                "sky.png.import",
            ],
        )
        self.assertEqual(files["player.gd"], b"class_name Player\nextends Node\n")
        self.assertIn(
            b'"class": &"Player"', files[".godot/global_script_class_cache.cfg"]
        )
        self.assertEqual(
            files[".godot/uid_cache.bin"],
            uid_cache(
                {
                    "main.tscn": "uid://b73qwse0wrl46",
                    "player.gd": "uid://c1od550e86gw1",
                    "sky.png": "uid://vj5ano28uc3c",
                }
            ),
        )
        self.assertEqual(
            files[".godot/extension_list.cfg"], b"res://native/native.gdextension\n"
        )
        self.assertEqual(files["project.binary"], b"ECFG\0\0\0\0")
        self.assertEqual(self.report["pack_conversion"], "none")

    def test_packs_only_the_import_of_an_imported_file(self) -> None:
        files = self.pack({"features": ["s3tc", "pc"]}, {"sky.png": b"png"})
        self.assertNotIn("sky.png", files)
        self.assertIn(".godot/imported/sky.png-1.s3tc.ctex", files)
        self.assertNotIn(".godot/imported/sky.png-1.etc2.ctex", files)

    def test_packs_the_uid_staging_gave_a_script(self) -> None:
        self.file("import/a.gd.uid", "uid://c1od550e86gw1\n")
        files = self.pack({"features": []}, {"a.gd": "extends Node\n"})
        self.assertEqual(files["a.gd.uid"], b"uid://c1od550e86gw1\n")
        self.assertEqual(
            files[".godot/uid_cache.bin"],
            uid_cache({"a.gd": "uid://c1od550e86gw1"}),
        )

    def test_the_pck_is_deterministic(self) -> None:
        members = {"a.gd": "extends Node\n", "sky.png": b"png"}
        first = self.pack({"features": []}, members)
        self.assertEqual(self.pack({"features": []}, members), first)
        self.assertEqual(
            pck_file_contents(self.root / "out.pck")["godot_version"], "4.7.2"
        )


if __name__ == "__main__":
    unittest.main()
