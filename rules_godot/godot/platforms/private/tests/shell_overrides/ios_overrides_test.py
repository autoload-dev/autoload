"""An application's own Info.plist keys, launch screen, privacy manifest and icons on iOS."""

import argparse
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.platforms.apple_bundle import application_bundle

_ROLES = ("shell", "overrides", "icon_composer")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for role in _ROLES:
        parser.add_argument("--" + role, nargs="+", required=True)
    return parser.parse_args(sys.argv[1:])


def _application(paths: list[str], work: Path) -> Path:
    (path,) = [Path(path) for path in paths if path.endswith((".app", ".ipa"))]
    return application_bundle(path, work)


class IosOverridesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        args = _arguments()
        cls.work = tempfile.TemporaryDirectory()
        cls.apps = {
            role: _application(getattr(args, role), Path(cls.work.name) / role)
            for role in _ROLES
        }
        cls.info = {
            role: plistlib.loads((app / "Info.plist").read_bytes())
            for role, app in cls.apps.items()
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.work.cleanup()

    def test_application_plist_keys_replace_the_shell_keys(self) -> None:
        self.assertIs(self.info["overrides"]["UIStatusBarHidden"], False)
        self.assertEqual(self.info["overrides"]["ExampleOverrideMarker"], "application")
        self.assertNotIn("ExampleOverrideMarker", self.info["shell"])

    def test_application_launch_storyboard_replaces_the_launch_screen(self) -> None:
        overrides, shell = self.info["overrides"], self.info["shell"]
        self.assertEqual(overrides["UILaunchStoryboardName"], "LaunchScreen")
        self.assertNotIn("UILaunchScreen", overrides)
        self.assertTrue((self.apps["overrides"] / "LaunchScreen.storyboardc").is_dir())
        self.assertIn("UILaunchScreen", shell)
        self.assertNotIn("UILaunchStoryboardName", shell)

    def test_application_privacy_manifest_replaces_the_shell_manifest(self) -> None:
        manifest = plistlib.loads(
            (self.apps["overrides"] / "PrivacyInfo.xcprivacy").read_bytes()
        )
        self.assertEqual(manifest["NSPrivacyTrackingDomains"], ["overrides.example.org"])
        # Godot's privacy manifest declares the engine's accessed APIs.
        self.assertNotIn("NSPrivacyAccessedAPITypes", manifest)
        shell = plistlib.loads(
            (self.apps["shell"] / "PrivacyInfo.xcprivacy").read_bytes()
        )
        self.assertIn("NSPrivacyAccessedAPITypes", shell)

    def renditions(self, role: str) -> set[str]:
        """The file names of the images the application's compiled asset catalog holds."""
        output = subprocess.run(
            ["/usr/bin/xcrun", "assetutil", "--info", self.apps[role] / "Assets.car"],
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout
        return {
            entry["RenditionName"]
            for entry in json.loads(output)
            if isinstance(entry, dict) and "RenditionName" in entry
        }

    def test_application_app_icons_replace_the_shell_icons(self) -> None:
        for role in _ROLES:
            with self.subTest(role=role):
                icons = self.info[role]["CFBundleIcons"]["CFBundlePrimaryIcon"]
                self.assertEqual(icons["CFBundleIconName"], "AppIcon")
        self.assertIn("icon_1024.png", self.renditions("overrides"))
        self.assertNotIn("icon_1024.png", self.renditions("shell"))

    def test_icon_composer_icon_is_the_app_icon(self) -> None:
        # actool compiles the Icon Composer icon into the catalog as an icon stack.
        self.assertIn("AppIcon.iconstack", self.renditions("icon_composer"))
        self.assertNotIn("AppIcon.iconstack", self.renditions("shell"))


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
