"""Check what both forms of a pack carry for its runtime besides the project's files."""

import os
import re
import unittest
from pathlib import Path

from tools.pck import pck_file_contents, pck_file_member

ROOT = (
    Path(os.environ["TEST_SRCDIR"])
    / os.environ["TEST_WORKSPACE"]
    / "godot/private/tests/pack_forms"
)
FORMS = ["godot", "none"]
# The packs for Android; their export has the feature tags of ETC2/ASTC and not S3TC/BPTC.
ANDROID_FORMS = ["android_godot", "android_none"]
_REMAP_PATH = re.compile(r'^path(?:\.([A-Za-z0-9_]+))?="res://([^"]+)"', re.MULTILINE)


def paths(form: str) -> set[str]:
    return set(pck_file_contents(ROOT / f"{form}_pack.pck", include_paths=True)["paths"])


def sidecar(form: str) -> str:
    """The texture's packed import sidecar."""
    return pck_file_member(ROOT / f"{form}_pack.pck", "main/tile.png.import").decode()


def remap_paths(form: str) -> dict[str, str]:
    """The paths the texture's packed sidecar names, by their remap feature tag."""
    return dict(_REMAP_PATH.findall(sidecar(form)))


class RuntimeInputsTest(unittest.TestCase):
    def test_a_translation_of_a_locale_that_needs_it_brings_the_support_data(
        self,
    ) -> None:
        for form in FORMS:
            with self.subTest(form=form):
                self.assertIn("icudt_godot.dat", paths(form))

    def test_imported_variants_follow_the_kept_remap_keys(self) -> None:
        for form in FORMS + ANDROID_FORMS:
            with self.subTest(form=form):
                packed = paths(form)
                self.assertNotIn("main/tile.png", packed)
                self.assertNotIn("[params]", sidecar(form))
                named = set(remap_paths(form).values())
                self.assertTrue(named)
                self.assertLessEqual(named, packed)
                # The variants of the feature tags the export lacks stay out.
                textures = {
                    path
                    for path in packed
                    if path.startswith(".godot/imported/tile.png-")
                }
                self.assertEqual(textures, named)

    def test_android_packs_carry_an_etc2_astc_variant(self) -> None:
        # The project leaves Godot's VRAM import settings at their defaults, under which
        # the editor imports only the format family its CPU prefers: S3TC/BPTC on macOS
        # and x86_64, ETC2/ASTC on Linux arm64. Without the formats the ruleset fixes,
        # the host's packs or the Android packs would find no variant of the texture.
        for form in ANDROID_FORMS:
            with self.subTest(form=form):
                self.assertTrue(remap_paths(form))
                self.assertLessEqual(set(remap_paths(form)), {"etc2", "astc"})

    def test_the_global_class_is_listed(self) -> None:
        for form in FORMS:
            with self.subTest(form=form):
                classes = pck_file_member(
                    ROOT / f"{form}_pack.pck", ".godot/global_script_class_cache.cfg"
                )
                self.assertIn(b'"class": &"RuntimeGreeter"', classes)


if __name__ == "__main__":
    unittest.main()
