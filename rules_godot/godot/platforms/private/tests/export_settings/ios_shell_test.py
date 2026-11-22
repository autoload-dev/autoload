"""Inspect the iOS shell files that Godot's export of a pack writes."""

import json
import os
import plistlib
import unittest
from pathlib import Path

PACKAGE = "godot/platforms/private/tests/export_settings"


class IosShellTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"] / PACKAGE
        )

    def plist(self, name: str, file: str = "Godot.plist") -> dict:
        path = self.root / (name + ".godot_shell") / file
        return plistlib.loads(path.read_bytes())

    def test_ios_shell_follows_project_settings(self) -> None:
        values = self.plist("ios_app_from_project_settings")
        scene = values["UIApplicationSceneManifest"]
        self.assertFalse(scene["UIApplicationSupportsMultipleScenes"])
        self.assertEqual(values["CFBundleDisplayName"], "Game & Test")
        # Godot's version of a project that sets none.
        self.assertEqual(values["CFBundleVersion"], "1.0.0")
        self.assertEqual(values["CFBundleShortVersionString"], "1.0.0")
        self.assertTrue(values["UIRequiresFullScreen"])
        self.assertTrue(values["UIStatusBarHidden"])
        self.assertEqual(
            values["UISupportedInterfaceOrientations"],
            ["UIInterfaceOrientationPortrait"],
        )
        self.assertEqual(values["UIRequiredDeviceCapabilities"], [])
        self.assertEqual(
            values["UILaunchScreen"],
            {"UIColorName": "LaunchScreenBackground", "UIImageName": "SplashImage"},
        )
        root = self.root / "ios_app_from_project_settings.godot_shell"
        color = json.loads(
            (
                root
                / "LaunchScreen.xcassets/LaunchScreenBackground.colorset/Contents.json"
            ).read_text()
        )
        # The project's boot splash color, Godot's default.
        self.assertEqual(
            color["colors"][0]["color"]["components"],
            {"alpha": "1.000", "blue": "0.140", "green": "0.140", "red": "0.140"},
        )
        privacy = self.plist("ios_app_from_project_settings", "PrivacyInfo.xcprivacy")
        self.assertEqual(
            [
                entry["NSPrivacyAccessedAPIType"]
                for entry in privacy["NSPrivacyAccessedAPITypes"]
            ],
            [
                "NSPrivacyAccessedAPICategoryFileTimestamp",
                "NSPrivacyAccessedAPICategorySystemBootTime",
                "NSPrivacyAccessedAPICategoryDiskSpace",
            ],
        )
        self.assertFalse(privacy["NSPrivacyTracking"])
        self.assertTrue(
            (root / "custom_engine_name.pck").read_bytes().startswith(b"GDPC")
        )

    def test_ios_shell_follows_export_options(self) -> None:
        values = self.plist("ios_app_with_export_options")
        self.assertEqual(values["CFBundleDisplayName"], "Fixture Game")
        self.assertEqual(values["CFBundleVersion"], "42")
        self.assertEqual(values["CFBundleShortVersionString"], "2.1")
        self.assertEqual(values["NSCameraUsageDescription"], "Scan & play")
        self.assertTrue(values["LSSupportsOpeningDocumentsInPlace"])
        self.assertEqual(values["ExtraKey"], "extra")
        self.assertFalse(values["UIRequiresFullScreen"])
        self.assertFalse(values["UIStatusBarHidden"])
        # Godot's landscape default; the default renderer needs an A12.
        self.assertEqual(
            values["UISupportedInterfaceOrientations"],
            ["UIInterfaceOrientationLandscapeLeft"],
        )
        self.assertEqual(
            values["UIRequiredDeviceCapabilities"],
            ["wifi", "iphone-ipad-minimum-performance-a12", "metal"],
        )
        privacy = self.plist("ios_app_with_export_options", "PrivacyInfo.xcprivacy")
        self.assertTrue(privacy["NSPrivacyTracking"])
        self.assertEqual(privacy["NSPrivacyTrackingDomains"], ["tracker.example.org"])
        self.assertEqual(
            privacy["NSPrivacyCollectedDataTypes"],
            [
                {
                    "NSPrivacyCollectedDataType": "NSPrivacyCollectedDataTypeEmailAddress",
                    "NSPrivacyCollectedDataTypeLinked": True,
                    "NSPrivacyCollectedDataTypePurposes": [
                        "NSPrivacyCollectedDataTypePurposeAnalytics",
                        "NSPrivacyCollectedDataTypePurposeAppFunctionality",
                    ],
                    "NSPrivacyCollectedDataTypeTracking": False,
                }
            ],
        )
        self.assertIn(
            {
                "NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryUserDefaults",
                "NSPrivacyAccessedAPITypeReasons": ["CA92.1"],
            },
            privacy["NSPrivacyAccessedAPITypes"],
        )


if __name__ == "__main__":
    unittest.main()
