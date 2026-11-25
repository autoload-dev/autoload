"""Godot's file naming: sidecars, UID files and hidden paths."""

import unittest

from tools.godot_files import (
    is_hidden,
    is_sidecar_named,
    is_uid_sidecar,
    sidecar_source,
    sidecars_of,
)

# The Python rows of the file naming rules; the error rows depend on declarations and
# belong to analysis.
_SOURCES = {
    "a.gd.uid": "a.gd",
    "t.png.import": "t.png",
    "dir/t.png.import": "dir/t.png",
    "notes.import": "notes",
    "Icon.PNG.Import": "Icon.PNG",
    "a.gd.uid.uid": None,
    "a.png.import.uid": None,
    ".uid": None,
    "dir/.import": None,
    "x.uidx": None,
    "a.gd.uid.UID": None,
    "y.imports": None,
    "native/x.gdextension": None,
    "data/table.so": None,
}


class GodotFilesTest(unittest.TestCase):
    def test_sidecar_source_follows_godots_naming_rule(self) -> None:
        self.assertEqual(_SOURCES, {path: sidecar_source(path) for path in _SOURCES})

    def test_sidecar_named_paths_are_never_resources(self) -> None:
        self.assertEqual(
            {"a.gd.uid", "a.gd.uid.uid", ".uid", "notes.import"},
            {
                path
                for path in (
                    "a.gd",
                    "a.gd.uid",
                    "a.gd.uid.uid",
                    ".uid",
                    "notes.import",
                    "x.uidx",
                )
                if is_sidecar_named(path)
            },
        )

    def test_sidecars_of_a_file_and_none_of_a_sidecar(self) -> None:
        self.assertEqual(("t.png.import", "t.png.uid"), sidecars_of("t.png"))
        self.assertEqual((), sidecars_of("a.gd.uid"))
        self.assertEqual((), sidecars_of("a.gd.UID"))

    def test_uid_sidecars_have_a_source(self) -> None:
        self.assertEqual(
            ["a.gd.UID", "a.gd.uid"],
            sorted(
                path
                for path in ("a.gd.uid", "a.gd.UID", "t.png.import", ".uid", "a.gd")
                if is_uid_sidecar(path)
            ),
        )

    def test_hidden_files_and_directories_begin_with_a_dot(self) -> None:
        self.assertEqual(
            [".gdignore", ".godot/imported/a.ctex", "main/.env", ".cache/a.png"],
            [
                path
                for path in (
                    ".gdignore",
                    ".godot/imported/a.ctex",
                    "main/.env",
                    ".cache/a.png",
                    "main/main.gd",
                    "report/template.html",
                )
                if is_hidden(path)
            ],
        )


if __name__ == "__main__":
    unittest.main()
