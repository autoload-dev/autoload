"""Strict parsing requirements for user-authored additional application metadata."""

import plistlib
import unittest

from tools.platforms import shell_apple


class AdditionalMetadataTest(unittest.TestCase):
    BASE = plistlib.dumps(
        {
            "CFBundleIdentifier": "org.example.game",
            "UIStatusBarHidden": True,
            "UIRequiresFullScreen": True,
        }
    ).decode()

    def test_boolean_overrides_and_additive_values(self) -> None:
        result = shell_apple._checked(
            self.BASE,
            "Info.plist",
            "<key>UIStatusBarHidden</key><false/><key>Game</key><array><string>custom</string></array>",
        )
        self.assertEqual(False, plistlib.loads(result.encode())["UIStatusBarHidden"])
        self.assertEqual(["custom"], plistlib.loads(result.encode())["Game"])

    def test_boolean_override_requires_boolean(self) -> None:
        with self.assertRaisesRegex(ValueError, "boolean"):
            shell_apple._checked(
                self.BASE,
                "Info.plist",
                "<key>UIStatusBarHidden</key><integer>0</integer>",
            )

    def test_protected_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "CFBundleIdentifier"):
            shell_apple._checked(
                self.BASE,
                "Info.plist",
                "<key>CFBundleIdentifier</key><string>other.game</string>",
            )

    def test_equal_cross_source_value(self) -> None:
        result = shell_apple._checked(
            self.BASE,
            "Info.plist",
            "<key>CFBundleIdentifier</key><string>org.example.game</string>",
        )
        self.assertEqual(
            "org.example.game", plistlib.loads(result.encode())["CFBundleIdentifier"]
        )

    def test_conflicting_library_fragments_in_either_order(self) -> None:
        fragments = [
            plistlib.dumps({"LibraryKey": value}).decode()
            for value in ["first", "second"]
        ]
        for ordered in [fragments, list(reversed(fragments))]:
            with self.assertRaisesRegex(ValueError, "LibraryKey"):
                shell_apple.merge_plists(self.BASE, ordered)

    def test_library_cannot_change_boolean_override(self) -> None:
        fragment = plistlib.dumps({"UIStatusBarHidden": False}).decode()
        with self.assertRaisesRegex(ValueError, "UIStatusBarHidden"):
            shell_apple.merge_plists(self.BASE, [fragment])

    def test_additional_content_cannot_change_an_application_owned_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "MinimumOSVersion"):
            shell_apple._checked(
                "<plist><dict/></plist>",
                "Info.plist",
                "<key>MinimumOSVersion</key><string>12.0</string>",
                owned={"MinimumOSVersion": "15.0"},
            )

    def test_boolean_element_cannot_have_text(self) -> None:
        with self.assertRaisesRegex(ValueError, "boolean"):
            shell_apple._checked(
                "<plist><dict><key>x</key><true>wrong</true></dict></plist>", "Info.plist"
            )

    def test_duplicate_top_level_key_is_rejected(self) -> None:
        text = '<plist version="1.0"><dict><key>x</key><true/><key>x</key><false/></dict></plist>'
        with self.assertRaisesRegex(ValueError, "[Dd]uplicate"):
            shell_apple._checked(text, "Info.plist")

    def test_duplicate_nested_key_is_rejected(self) -> None:
        text = '<plist version="1.0"><dict><key>nested</key><dict><key>x</key><true/><key>x</key><true/></dict></dict></plist>'
        with self.assertRaisesRegex(ValueError, "[Dd]uplicate"):
            shell_apple._checked(text, "Info.plist")

    def test_malformed_structure_is_rejected(self) -> None:
        for text, message in [
            ("<dict/>", "Expected a plist root"),
            ("<plist><dict/><dict/></plist>", "Expected one top-level plist dictionary"),
            ("<plist><array/></plist>", "Expected one top-level plist dictionary"),
            ("<plist><dict><key>x</key></dict></plist>", "key/value sequence"),
            ("<plist><dict><string/><key>x</key></dict></plist>", "key/value sequence"),
            (
                "<plist><dict><key>x</key><key>y</key></dict></plist>",
                "key/value sequence",
            ),
            (
                "<plist><dict><key>x</key><array><key>y</key></array></dict></plist>",
                "Malformed plist array",
            ),
            (
                "<plist><dict><key>x</key><string><true/></string></dict></plist>",
                "Unexpected child in plist scalar string",
            ),
        ]:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                shell_apple._checked(text, "Info.plist")

    def test_unknown_xml_element_is_rejected(self) -> None:
        text = (
            '<plist version="1.0"><dict><unrecognized/><key>x</key><true/></dict></plist>'
        )
        with self.assertRaisesRegex(ValueError, "[Uu]nknown|[Uu]nsupported"):
            shell_apple._checked(text, "Info.plist")


if __name__ == "__main__":
    unittest.main()
