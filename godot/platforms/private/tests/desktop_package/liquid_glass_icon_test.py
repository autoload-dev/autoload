"""A macOS bundle carries the asset catalog actool compiles from the pack's .icon."""

import plistlib
import sys
import unittest
from pathlib import Path


class LiquidGlassIconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # The bundle lies beside the application's launcher among the arguments.
        (bundle,) = [
            Path(arg).with_suffix(".app")
            for arg in sys.argv[1:]
            if Path(arg).with_suffix(".app").is_dir()
        ]
        cls.contents = bundle / "Contents"

    def test_resources_hold_the_compiled_asset_catalog(self) -> None:
        catalog = (self.contents / "Resources/Assets.car").read_bytes()
        self.assertTrue(catalog.startswith(b"BOMStore"))

    def test_info_plist_names_the_icon(self) -> None:
        info = plistlib.loads((self.contents / "Info.plist").read_bytes())
        self.assertEqual("game", info["CFBundleIconName"])


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
