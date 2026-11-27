import tempfile
import unittest
from pathlib import Path

from tools.pack.pck import add_pck_files, pck_contents, pck_file_contents
from tools.pack.tests.empty_pck import pck_bytes, write_pck


class PckTest(unittest.TestCase):
    def test_added_pck_files_replace_and_extend_godots_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            godot = base / "godot.pck"
            add_pck_files(
                write_pck(base / "empty.pck"),
                godot,
                {"a.txt": b"a", ".godot/extension_list.cfg": b"res://x.gdextension\n"},
            )
            files = {
                ".godot/extension_list.cfg": b"res://x.gdextension\nres://y.gdextension\n",
                "y.gdextension": b"[configuration]\n",
            }
            first, second = base / "first.pck", base / "second.pck"
            add_pck_files(godot, first, files)
            add_pck_files(godot, second, files)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            contents = pck_file_contents(first, include_paths=True)
            self.assertEqual(
                [".godot/extension_list.cfg", "a.txt", "y.gdextension"],
                contents["paths"],
            )
            self.assertEqual(
                ["res://x.gdextension", "res://y.gdextension"], contents["extension_list"]
            )
            self.assertEqual(
                {"y.gdextension": "[configuration]\n"}, contents["extension_descriptors"]
            )

    def test_mobile_pack_inspector_rejects_legacy_engines_and_formats(self) -> None:
        self.assertEqual(pck_contents(pck_bytes())["godot_version"], "4.7.2")
        for data in [
            pck_bytes(version=2),
            pck_bytes(version=3),
            pck_bytes(engine=(4, 7, 1)),
        ]:
            with self.assertRaisesRegex(ValueError, "PCK v4"):
                pck_contents(data)


if __name__ == "__main__":
    unittest.main()
