"""An application's own manifest, theme and launcher icon replace the Android shell's."""

import argparse
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

_ROLES = ("shell", "overrides")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aapt", type=Path, required=True)
    for role in _ROLES:
        parser.add_argument("--" + role, nargs="+", required=True)
    return parser.parse_args(sys.argv[1:])


def _apk(paths: list[str]) -> Path:
    (path,) = [
        Path(path)
        for path in paths
        if path.endswith(".apk") and not path.endswith("_unsigned.apk")
    ]
    return path


def _aapt(aapt: Path, *args: str | Path) -> str:
    return subprocess.check_output([aapt.absolute(), *args], text=True)


def _style_items(resources: str, style: str) -> dict[str, str]:
    """The resource names a style's items reference, by the item's attribute ID."""
    names = dict(re.findall(r"resource (0x[0-9a-f]+) [\w.]+:(\w+/\w+)", resources))
    block = resources.split(f":style/{style}: <bag>", 1)[1].split("resource 0x", 1)[0]
    return {
        key: names.get(value, value)
        for key, value in re.findall(
            r"\(Key=(0x[0-9a-f]+)\):[^\n]*?(0x[0-9a-f]{8})", block
        )
    }


class AndroidOverridesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        args = _arguments()
        cls.apks = {role: _apk(getattr(args, role)) for role in _ROLES}
        cls.manifests = {
            role: _aapt(args.aapt, "dump", "xmltree", apk, "AndroidManifest.xml")
            for role, apk in cls.apks.items()
        }
        cls.resources = {
            role: _aapt(args.aapt, "dump", "--values", "resources", apk)
            for role, apk in cls.apks.items()
        }

    def test_application_manifest_is_the_main_manifest(self) -> None:
        manifest = self.manifests["overrides"]
        # Its own entries, the shell's activity, version and permissions of the pack.
        self.assertIn("org.example.overrides.marker", manifest)
        self.assertIn("org.example.overrides.OWN", manifest)
        self.assertIn("com.godot.game.GodotApp", manifest)
        self.assertRegex(manifest, r"android:versionCode\([^)]*\)=\(type 0x10\)0x1\b")
        # A library's permission merges below it.
        self.assertIn("org.example.composition.PERMISSION", manifest)
        # Its tools:node="remove" removed the shell's element; its activity attribute
        # replaced the shell's (portrait is 0x1, Godot's landscape default 0x0).
        self.assertNotIn("org.godotengine.rendering.method", manifest)
        self.assertIn("org.godotengine.rendering.method", self.manifests["shell"])
        orientation = r"android:screenOrientation\([^)]*\)=\(type 0x10\)0x{}\b"
        self.assertRegex(manifest, orientation.format(1))
        self.assertRegex(self.manifests["shell"], orientation.format(0))

    def test_application_theme_replaces_the_splash_theme(self) -> None:
        window_background = "0x01010054"
        overridden = _style_items(self.resources["overrides"], "GodotAppSplashTheme")
        self.assertEqual(overridden.get(window_background), "drawable/start")
        shell = _style_items(self.resources["shell"], "GodotAppSplashTheme")
        self.assertNotIn(window_background, shell)

    def test_application_icon_replaces_one_density(self) -> None:
        with zipfile.ZipFile(self.apks["overrides"]) as apk:
            icons = sorted(name for name in apk.namelist() if "/icon." in name)
        self.assertIn("res/mipmap-xxxhdpi-v4/icon.png", icons)
        self.assertNotIn("res/mipmap-xxxhdpi-v4/icon.webp", icons)
        self.assertIn("res/mipmap-xxhdpi-v4/icon.webp", icons)
        with zipfile.ZipFile(self.apks["shell"]) as apk:
            self.assertIn("res/mipmap-xxxhdpi-v4/icon.webp", apk.namelist())


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
