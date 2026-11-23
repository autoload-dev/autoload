"""Inspect the Android bootstrap that Godot's export of a pack writes the shell files of."""

import os
import unittest
from pathlib import Path
from xml.etree import ElementTree

from tools.platforms import shell_android

ANDROID = "{http://schemas.android.com/apk/res/android}"
PACKAGE = "godot/platforms/private/tests/export_settings"


class AndroidBootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"] / PACKAGE
        )

    def android(self, name: str) -> tuple[ElementTree.Element, list[str]]:
        """The bootstrap's manifest and the command line of its assets/_cl_ file."""
        root = self.root / (name + ".godot_bootstrap")
        manifest = ElementTree.parse(root / "AndroidManifest.xml").getroot()
        args = shell_android.parse_command_line_file((root / "assets/_cl_").read_bytes())
        return manifest, args

    def test_android_bootstrap_follows_project_settings(self) -> None:
        manifest, args = self.android("android_app_from_project_settings")
        root = self.root / "android_app_from_project_settings.godot_bootstrap"
        self.assertTrue((root / "assets/main.pck").read_bytes().startswith(b"GDPC"))
        application = manifest.find("application")
        activity = manifest.find("application/activity")
        assert application is not None and activity is not None
        self.assertEqual(activity.get(ANDROID + "name"), "com.godot.game.GodotApp")
        self.assertEqual(activity.get(ANDROID + "exported"), "false")
        # The bootstrap compiles the pack minor's copy of Godot's template activity.
        engine = (
            Path(os.environ["TEST_SRCDIR"])
            / os.environ["TEST_WORKSPACE"]
            / "godot/private/engine/android"
        )
        for source in ["godot_4_7/GodotApp.java", "BuildConfig.java"]:
            self.assertTrue((engine / source).is_file(), source)
        self.assertIn("orientation", activity.get(ANDROID + "configChanges", ""))
        self.assertEqual(activity.get(ANDROID + "launchMode"), "singleInstancePerTask")
        self.assertEqual(activity.get(ANDROID + "windowSoftInputMode"), "adjustResize")
        # From the project's config/name, handheld/orientation and size/resizable.
        self.assertEqual(application.get(ANDROID + "label"), "Game & Test")
        self.assertEqual(activity.get(ANDROID + "screenOrientation"), "portrait")
        self.assertEqual(activity.get(ANDROID + "resizeableActivity"), "false")
        self.assertEqual(application.get(ANDROID + "icon"), "@mipmap/icon")
        self.assertEqual(application.get(ANDROID + "appCategory"), "game")
        self.assertEqual(application.get(ANDROID + "isGame"), "true")
        self.assertEqual(application.get(ANDROID + "extractNativeLibs"), "false")
        self.assertEqual(
            activity.get(ANDROID + "theme"),
            "@style/GodotAppSplashTheme",
        )
        self.assertEqual(manifest.get(ANDROID + "versionCode"), "1")
        self.assertEqual(manifest.get(ANDROID + "versionName"), "1.0.0")
        self.assertEqual(manifest.get(ANDROID + "installLocation"), "auto")
        self.assertEqual(manifest.findall("uses-permission"), [])
        # The Compatibility renderer needs no Vulkan.
        self.assertEqual(
            [f.get(ANDROID + "name") for f in manifest.findall("uses-feature")],
            [None],
        )
        meta = {
            element.get(ANDROID + "name"): element.get(ANDROID + "value")
            for element in manifest.iter("meta-data")
        }
        self.assertEqual(meta["org.godotengine.editor.version"], "4.7.2.stable")
        self.assertEqual(meta["org.godotengine.rendering.method"], "gl_compatibility")
        self.assertEqual(
            args,
            [
                "--main-pack",
                "res://main.pck",
                "--xr_mode_regular",
                "--xr-mode",
                "off",
                # Godot's own export starts immersive with --fullscreen.
                "--fullscreen",
                "--background_color",
                "#000000",
            ],
        )

    def test_android_bootstrap_follows_export_options(self) -> None:
        manifest, args = self.android("android_app_with_export_options")
        application = manifest.find("application")
        alias = manifest.find("application/activity-alias")
        assert application is not None and alias is not None
        self.assertEqual(application.get(ANDROID + "label"), "Configured & Game")
        self.assertEqual(application.get(ANDROID + "appCategory"), "social")
        self.assertEqual(application.get(ANDROID + "isGame"), "false")
        self.assertEqual(application.get(ANDROID + "allowBackup"), "true")
        self.assertEqual(application.get(ANDROID + "hasFragileUserData"), "true")
        self.assertEqual(
            [p.get(ANDROID + "name") for p in manifest.findall("uses-permission")],
            [
                "android.permission.INTERNET",
                "android.permission.VIBRATE",
                "org.example.permission.CUSTOM",
            ],
        )
        screens = manifest.find("supports-screens")
        assert screens is not None
        self.assertEqual(screens.get(ANDROID + "smallScreens"), "false")
        self.assertEqual(screens.get(ANDROID + "normalScreens"), "true")
        self.assertIn(
            "android.intent.category.LEANBACK_LAUNCHER",
            [c.get(ANDROID + "name") for c in alias.iter("category")],
        )
        self.assertEqual(manifest.get(ANDROID + "versionCode"), "7")
        self.assertEqual(manifest.get(ANDROID + "versionName"), "2.0")
        # The default renderers request Vulkan, falling back to OpenGL.
        features = {
            f.get(ANDROID + "name"): f.get(ANDROID + "required")
            for f in manifest.findall("uses-feature")
        }
        self.assertEqual(features["android.hardware.vulkan.level"], "false")
        self.assertEqual(features["android.hardware.vulkan.version"], "false")
        # command_line/extra_args come before Godot's own export flags.
        self.assertEqual(
            args[1:6],
            [
                "res://main.pck",
                "--verbose",
                "--audio-driver",
                "Dummy",
                "--xr_mode_regular",
            ],
        )
        self.assertNotIn("--fullscreen", args)
        self.assertIn("--edge_to_edge", args)
        self.assertIn("#ff8000", args)


if __name__ == "__main__":
    unittest.main()
