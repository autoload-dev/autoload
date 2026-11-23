"""Desktop bundles run their runtime over the pack and carry what Godot's export decides."""

import plistlib
import subprocess
import sys
import unittest
from pathlib import Path


def _bundle(suffix: str) -> Path:
    """Return the bundle beside the application launcher among the test's arguments."""
    (bundle,) = [
        Path(arg).with_suffix(suffix)
        for arg in sys.argv[1:]
        if Path(arg).with_suffix(suffix).is_dir()
    ]
    return bundle


class DesktopBundlesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.linux = _bundle(".bundle")
        cls.contents = _bundle(".app") / "Contents"

    def test_linux_bundle_runs_its_runtime_over_the_pack(self) -> None:
        self.assertEqual(
            subprocess.check_output([str(self.linux / "Game")]), b"package fixture\n"
        )

    def test_macos_bundle_runs_its_runtime_over_godots_export(self) -> None:
        self.assertTrue(
            subprocess.check_output([str(self.contents / "MacOS/Game")]).startswith(
                b"GDPC"
            )
        )

    def test_info_plist_takes_the_project_name_and_version(self) -> None:
        info = plistlib.loads((self.contents / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleDisplayName"], "Fixture Game")
        self.assertEqual(info["CFBundleShortVersionString"], "2.3.4")
        self.assertEqual(info["CFBundleIdentifier"], "org.example.game")

    def test_project_without_icon_gets_godots_default_icon(self) -> None:
        info = plistlib.loads((self.contents / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleIconFile"], "icon.icns")
        self.assertTrue(
            (self.contents / "Resources/icon.icns").read_bytes().startswith(b"icns")
        )

    def test_privacy_manifest_declares_nothing(self) -> None:
        privacy = self.contents / "Resources/PrivacyInfo.xcprivacy"
        self.assertEqual(
            plistlib.loads(privacy.read_bytes()),
            {
                "NSPrivacyAccessedAPITypes": [],
                "NSPrivacyCollectedDataTypes": [],
                "NSPrivacyTracking": False,
                "NSPrivacyTrackingDomains": [],
            },
        )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
