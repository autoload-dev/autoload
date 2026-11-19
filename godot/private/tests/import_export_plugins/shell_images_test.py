"""Check the icons and splash images Godot rendered for the shells of a pack's exports."""

import json
import os
import struct
import unittest
from pathlib import Path

PACKAGE = "godot/private/tests/import_export_plugins"


class ExportFactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"]

    def images(self, name: str) -> dict:
        path = self.root / PACKAGE / (name + ".json")
        return json.loads(path.read_text())

    def png_size(self, path: Path) -> tuple[int, int]:
        data = path.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        return struct.unpack(">II", data[16:24])

    def test_android_debug_export_renders_icons_and_splash(self) -> None:
        images = self.images("android_debug_images")
        (icons,) = images["icons"]
        res = self.root / icons
        for density in ["mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"]:
            for name in ["icon", "icon_foreground"]:
                path = res / f"mipmap-{density}-v4/{name}.webp"
                self.assertEqual(path.read_bytes()[8:12], b"WEBP", path)
        self.assertTrue((res / "mipmap/icon.webp").is_file())
        # Without background and monochrome options, the engine's defaults stay.
        self.assertFalse((res / "mipmap/icon_background.webp").exists())
        adaptive = (res / "mipmap-anydpi-v26/icon.xml").read_text()
        self.assertIn(
            '<foreground android:drawable="@mipmap/icon_foreground"/>', adaptive
        )
        self.assertNotIn("monochrome", adaptive)
        # The splash screen shows the launcher icon's foreground.
        (splash,) = images["splash"]
        drawables = self.root / splash / "drawable"
        self.assertEqual((drawables / "splash_icon.webp").read_bytes()[8:12], b"WEBP")
        self.assertFalse((drawables / "splash_branding_image.webp").exists())

    def test_ios_release_export_renders_icons_and_splash(self) -> None:
        images = self.images("ios_release_images")
        icons = {Path(icon).name: self.root / icon for icon in images["icons"]}
        catalog = json.loads(icons["Contents.json"].read_text())
        self.assertEqual(len(catalog["images"]), 16)
        self.assertIn(
            {
                "idiom": "universal",
                "platform": "ios",
                "size": "1024x1024",
                "filename": "Icon-1024.png",
            },
            catalog["images"],
        )
        self.assertEqual(self.png_size(icons["Icon-1024.png"]), (1024, 1024))
        self.assertEqual(self.png_size(icons["Icon-167.png"]), (167, 167))
        # Without a splash image of its own, the launch screen shows Godot's.
        splash = {Path(image).name: self.root / image for image in images["splash"]}
        self.assertEqual(
            sorted(splash), ["Contents.json", "splash@2x.png", "splash@3x.png"]
        )
        self.assertEqual(splash["splash@2x.png"].read_bytes()[:4], b"\x89PNG")

    def test_macos_release_export_renders_its_icon(self) -> None:
        (icons,) = self.images("macos_release_images")["icons"]
        self.assertEqual((self.root / icons / "icon.icns").read_bytes()[:4], b"icns")


if __name__ == "__main__":
    unittest.main()
