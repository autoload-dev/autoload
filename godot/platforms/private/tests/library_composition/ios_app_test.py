"""An iOS application carries what its project's add-on and extension bring."""

import sys
import tempfile
import unittest
from pathlib import Path

from godot.platforms.private.tests.library_composition.ios_apps import (
    defined_symbols,
    framework_binary,
    unpacked,
)


class IosAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.app, cls.info, executable = unpacked(sys.argv[1:], Path(directory.name))
        cls.symbols = defined_symbols(executable)
        cls.extension_symbols = defined_symbols(framework_binary(cls.app, "hello"))

    def test_executable_links_the_libraries_of_the_addon(self) -> None:
        for symbol in ("rules_godot_example_controllers", "rules_godot_example_swift"):
            self.assertIn(symbol, self.symbols)

    def test_extension_framework_links_the_extension_and_its_deps(self) -> None:
        for symbol in ("rules_godot_library_init", "rules_godot_hello_support"):
            self.assertIn(symbol, self.extension_symbols)

    def test_bundle_carries_the_libraries_resources(self) -> None:
        for path in (
            "Assets.car",
            "PrivacyInfo.xcprivacy",
            "addon_notice.txt",
            # The extension's SDK resource bundle, which no platform_deps names.
            "hello_sdk_resources.bundle/hello_sdk_notice.txt",
        ):
            self.assertTrue((self.app / path).exists(), path)

    def test_info_plist_merges_the_addon_fragment(self) -> None:
        for key in (
            "CFBundleIcons",
            "GCSupportsControllerUserInteraction",
            "UILaunchScreen",
        ):
            self.assertIn(key, self.info)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
