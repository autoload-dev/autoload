"""The shell files godot_shell writes from an export's facts and the rules' values."""

import copy
import json
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from tools.platforms import shell_android, shell_apple
from tools.platforms.shell_common import Facts, fill, set_off

ANDROID = "{http://schemas.android.com/apk/res/android}"
# Godot 4.7.2's facts of default Android, iOS and macOS exports, trimmed to the options
# and settings the shell writers read; the engine profile is the one the rules pass, which
# the test's first argument names.
TESTDATA = Path(__file__).parent / "testdata/godot_shell"
FACTS = {
    operating_system: json.loads(
        (TESTDATA / f"{operating_system}_facts.json").read_text()
    )
    for operating_system in ["android", "ios", "macos"]
}
PROFILE = json.loads(Path(sys.argv.pop(1)).read_text())
RELEASE = {"explicit": [], "app_version": "", "build_number": 0}


def facts(
    operating_system: str,
    options: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> Facts:
    """The facts of an export for the operating system with other option and setting values."""
    data = copy.deepcopy(FACTS[operating_system])
    for name in options or {}:
        if name not in data["options"]:
            raise KeyError(f"The test data has no export option {name}")
    data["options"] |= options or {}
    data["settings"] |= settings or {}
    # Godot's get_version returns a version option the pack sets.
    data["versions"] |= {
        name: value for name, value in (options or {}).items() if name in data["versions"]
    }
    return Facts(data)


def manifest(data: Facts, **values: Any) -> ElementTree.Element:
    values = {
        "profile": PROFILE["android"],
        "fallback_name": "Target",
        "editor_version": "4.7.2.stable",
        **RELEASE,
        **values,
    }
    return ElementTree.fromstring(shell_android.manifest(data, values))


def ios_plist(data: Facts, **values: Any) -> dict:
    values = {
        "profile": PROFILE["ios"],
        "fallback_name": "Target",
        **RELEASE,
        **values,
    }
    return plistlib.loads(shell_apple.ios_plist(data, values).encode())


class GodotShellTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_unknown_export_option_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "no export option unknown/option"):
            facts("android").option("unknown/option")

    def test_declared_permissions(self) -> None:
        declared = shell_android.declared_permissions(
            facts(
                "android",
                {
                    "permissions/vibrate": True,
                    "permissions/custom_permissions": [" org.example.CUSTOM ", ""],
                },
            )
        )
        self.assertEqual(declared, ["android.permission.VIBRATE", "org.example.CUSTOM"])
        block = set_off(
            shell_android.permission_entries(declared, {"org.example.CUSTOM": "32"})
        )
        root = ElementTree.fromstring(
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
            + block
            + "</manifest>"
        )
        self.assertEqual(
            [
                (element.get(ANDROID + "name"), element.get(ANDROID + "maxSdkVersion"))
                for element in root
            ],
            [("android.permission.VIBRATE", None), ("org.example.CUSTOM", "32")],
        )
        self.assertEqual(set_off([]), "")

    def test_export_options_win_over_release_settings(self) -> None:
        release = {"app_version": "2.3.4", "build_number": 57}
        root = manifest(facts("android"), **release)
        self.assertEqual(root.get(ANDROID + "versionCode"), "57")
        self.assertEqual(root.get(ANDROID + "versionName"), "2.3.4")
        configured = facts("android", {"version/code": 7, "version/name": "2.0"})
        root = manifest(configured, explicit=["version/code", "version/name"], **release)
        self.assertEqual(root.get(ANDROID + "versionCode"), "7")
        self.assertEqual(root.get(ANDROID + "versionName"), "2.0")
        # Without either, Godot's version of a project that sets none.
        root = manifest(facts("android"))
        self.assertEqual(root.get(ANDROID + "versionName"), "1.0.0")
        self.assertEqual(root.get(ANDROID + "versionCode"), "1")

    def test_android_checks_what_stores_reject(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "versionCode must be from 1 to 2100000000"
        ):
            manifest(facts("android", {"version/code": 2100000001}))
        with self.assertRaisesRegex(ValueError, "XR exports"):
            shell_android.command_line(
                facts("android", {"xr_features/xr_mode": 1}),
                {"profile": PROFILE["android"]},
            )

    def test_android_command_line_file_is_godots_encoding(self) -> None:
        values = {"profile": PROFILE["android"]}
        data = shell_android.command_line_file(facts("android"), values)
        # Godot's encoding: a little-endian count, then each argument's byte length
        # and UTF-8 bytes.
        self.assertEqual(
            data[:4],
            len(shell_android.command_line(facts("android"), values)).to_bytes(
                4, "little"
            ),
        )
        args = shell_android.parse_command_line_file(data)
        self.assertEqual(args, shell_android.command_line(facts("android"), values))
        self.assertEqual(args[:2], ["--main-pack", "res://main.pck"])

    def test_android_transparency_makes_the_background_transparent(self) -> None:
        values = {"profile": PROFILE["android"]}
        allowed = {"display/window/per_pixel_transparency/allowed": True}
        args = shell_android.command_line(facts("android", settings=allowed), values)
        # Godot's Gradle export, whose themes this shell writes, passes a
        # transparent color as the system bars' fallback.
        self.assertEqual(args[args.index("--background_color") + 1], "#00000000")
        items = {
            item.get("name"): item.text
            for item in ElementTree.fromstring(
                shell_android.themes(facts("android", settings=allowed), values)
            ).iter("item")
        }
        self.assertEqual(items["android:windowBackground"], "@android:color/transparent")

    def test_android_custom_theme_attributes_extend_the_themes(self) -> None:
        values = {"profile": PROFILE["android"]}
        configured = facts(
            "android",
            {
                "gradle_build/custom_theme_attributes": {
                    "android:windowLightStatusBar": "true",
                    'android:quoted"&name': "<value>",
                    "[splash]android:windowSplashScreenIconBackgroundColor": "#123456",
                    # Unlike the main theme's, the splash screen's own may be replaced.
                    "[splash]android:windowSplashScreenBackground": "#abcdef",
                    # Godot's own options and project settings keep these.
                    "android:windowBackground": "#ffffff",
                    "[splash]postSplashScreenTheme": "@style/Other",
                    "[splash]android:windowIsTranslucent": "true",
                }
            },
        )
        root = ElementTree.fromstring(shell_android.themes(configured, values))
        styles = {
            style.get("name"): {
                item.get("name"): item.text for item in style.iter("item")
            }
            for style in root.iter("style")
        }
        main, splash = styles["GodotAppMainTheme"], styles["GodotAppSplashTheme"]
        self.assertEqual(main["android:windowLightStatusBar"], "true")
        self.assertEqual(main['android:quoted"&name'], "<value>")
        self.assertEqual(main["android:windowBackground"], "#000000")
        self.assertEqual(
            splash["android:windowSplashScreenIconBackgroundColor"], "#123456"
        )
        self.assertEqual(splash["android:windowSplashScreenBackground"], "#abcdef")
        self.assertEqual(splash["postSplashScreenTheme"], "@style/GodotAppMainTheme")
        self.assertEqual(splash["android:windowIsTranslucent"], "false")
        self.assertNotIn("[splash]android:windowSplashScreenIconBackgroundColor", main)

    def test_android_application_styles_replace_the_shell_styles(self) -> None:
        values = {"profile": PROFILE["android"]}
        overrides = self.root / "themes.xml"
        overrides.write_text(
            "<resources>"
            '<style name="GodotAppSplashTheme" parent="Theme.SplashScreen">'
            '<item name="android:windowBackground">@drawable/start</item></style>'
            '<color name="GodotAppMainTheme">#000000</color>'
            "</resources>"
        )
        text = shell_android.themes(facts("android"), values, [overrides])
        styles = [
            style.get("name") for style in ElementTree.fromstring(text).iter("style")
        ]
        # The style replaces the shell's whole style; a color of that name is no style.
        self.assertEqual(styles, ["GodotAppMainTheme"])
        unchanged = shell_android.themes(facts("android"), values)
        self.assertEqual(
            [s.get("name") for s in ElementTree.fromstring(unchanged).iter("style")],
            ["GodotAppMainTheme", "GodotAppSplashTheme"],
        )

    def main_manifest(self, text: str, **options: Any) -> ElementTree.Element:
        consumer = self.root / "AndroidManifest.xml"
        consumer.write_text(text)
        values = {
            "profile": PROFILE["android"],
            "fallback_name": "Target",
            "editor_version": "4.7.2.stable",
            **RELEASE,
        }
        declared = {
            "permissions/vibrate": True,
            "permissions/custom_permissions": ["org.example.DECLARED"],
        }
        shell = shell_android.manifest(facts("android", declared | options), values)
        return ElementTree.fromstring(
            shell_android.main_manifest(
                shell, consumer, {"versionCode": "the version/code export option"}
            )
        )

    def test_android_application_manifest_is_the_main_manifest(self) -> None:
        tools = "{" + shell_android.TOOLS_NAMESPACE + "}"
        root = self.main_manifest(
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android"\n'
            '    xmlns:tools="http://schemas.android.com/tools"\n'
            '    android:installLocation="preferExternal">\n'
            "    <!-- The application's own entries. -->\n"
            '    <uses-permission android:name="android.permission.VIBRATE"\n'
            '        tools:node="remove" />\n'
            "    <application>\n"
            '        <activity android:name="com.godot.game.GodotApp"\n'
            '            android:theme="@style/Start" tools:replace="android:theme" />\n'
            "    </application>\n"
            "</manifest>\n"
        )
        # The application's attributes win; the shell fills the others.
        self.assertEqual(root.get(ANDROID + "installLocation"), "preferExternal")
        self.assertEqual(root.get(ANDROID + "versionCode"), "1")
        sdk = root.find("uses-sdk")
        assert sdk is not None
        self.assertEqual(
            sdk.get(ANDROID + "minSdkVersion"), PROFILE["android"]["min_sdk"]
        )
        permissions = {
            element.get(ANDROID + "name"): element.get(tools + "node")
            for element in root.findall("uses-permission")
        }
        # Its removal stays the only entry of VIBRATE; the shell's other permissions are
        # added.
        self.assertEqual(
            permissions,
            {"android.permission.VIBRATE": "remove", "org.example.DECLARED": None},
        )
        activity = root.find("application/activity")
        assert activity is not None
        self.assertEqual(activity.get(tools + "replace"), "android:theme")

    def test_android_application_permissions_match_by_element(self) -> None:
        root = self.main_manifest(
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
            '<uses-permission-sdk-23 android:name="android.permission.VIBRATE" />'
            "</manifest>"
        )
        # A permission for Android 6 and later leaves the shell's unconditional one.
        self.assertEqual(
            [e.get(ANDROID + "name") for e in root.findall("uses-permission")],
            ["android.permission.VIBRATE", "org.example.DECLARED"],
        )

    def test_android_application_manifest_keeps_its_uses_sdk_markers(self) -> None:
        root = self.main_manifest(
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
            'xmlns:tools="http://schemas.android.com/tools">'
            '<uses-sdk tools:overrideLibrary="org.example.sdk" /></manifest>'
        )
        sdks = root.findall("uses-sdk")
        self.assertEqual(len(sdks), 1)
        self.assertEqual(
            sdks[0].get("{" + shell_android.TOOLS_NAMESPACE + "}overrideLibrary"),
            "org.example.sdk",
        )
        self.assertEqual(
            sdks[0].get(ANDROID + "targetSdkVersion"), PROFILE["android"]["target_sdk"]
        )

    def test_android_application_manifest_must_not_set_owned_values(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "sets android:versionCode on <manifest>.*version/code"
        ):
            self.main_manifest(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
                'android:versionCode="7" />'
            )

    def test_android_storage_permissions_end_at_android_10(self) -> None:
        def limits(**options: bool) -> dict[str | None, str | None]:
            root = manifest(
                facts("android", {f"permissions/{k}": v for k, v in options.items()})
            )
            return {
                element.get(ANDROID + "name"): element.get(ANDROID + "maxSdkVersion")
                for element in root.findall("uses-permission")
            }

        storage = "android.permission.%s_EXTERNAL_STORAGE"
        self.assertEqual(
            limits(read_external_storage=True, write_external_storage=True),
            {storage % "READ": None, storage % "WRITE": "29"},
        )
        # Beside MANAGE_EXTERNAL_STORAGE the read permission ends there too.
        self.assertEqual(
            limits(read_external_storage=True, manage_external_storage=True),
            {storage % "MANAGE": None, storage % "READ": "29"},
        )

    def test_android_activity_is_godots_template_activity(self) -> None:
        root = manifest(facts("android", {"package/show_in_android_tv": True}))
        self.assertEqual(root.get("package"), "com.godot.game")
        activity = root.find("application/activity")
        alias = root.find("application/activity-alias")
        assert activity is not None and alias is not None
        self.assertEqual(activity.get(ANDROID + "name"), "com.godot.game.GodotApp")
        self.assertEqual(activity.get(ANDROID + "exported"), "false")
        self.assertEqual(
            activity.get(ANDROID + "configChanges"),
            "|".join(PROFILE["android"]["config_changes"]),
        )
        self.assertEqual(list(activity), [])
        # Launchers start the activity through Godot's activity alias.
        self.assertEqual(alias.get(ANDROID + "name"), "com.godot.game.GodotAppLauncher")
        self.assertEqual(alias.get(ANDROID + "targetActivity"), "com.godot.game.GodotApp")
        self.assertEqual(alias.get(ANDROID + "exported"), "true")
        self.assertEqual(
            [c.get(ANDROID + "name") for c in alias.iter("category")],
            [
                "android.intent.category.DEFAULT",
                "android.intent.category.LAUNCHER",
                "android.intent.category.LEANBACK_LAUNCHER",
            ],
        )

    def test_android_splash_screen_follows_its_options(self) -> None:
        values = {"profile": PROFILE["android"]}
        themes = ElementTree.fromstring(shell_android.themes(facts("android"), values))
        items = {item.get("name"): item.text for item in themes.iter("item")}
        # Godot's default splash background is the adaptive icon's background.
        self.assertEqual(
            items["android:windowSplashScreenBackground"], "@mipmap/icon_background"
        )
        self.assertEqual(items["windowSplashScreenAnimatedIcon"], "@drawable/splash_icon")
        self.assertNotIn("android:windowSplashScreenBrandingImage", items)
        configured = facts(
            "android",
            {
                "splash_screen/background_color": [0.0, 0.0, 1.0, 1.0],
                "splash_screen/icon": "res://splash.xml",
                "splash_screen/branding_image": "res://brand.png",
            },
        )
        themes = ElementTree.fromstring(shell_android.themes(configured, values))
        items = {item.get("name"): item.text for item in themes.iter("item")}
        self.assertEqual(items["android:windowSplashScreenBackground"], "#0000ff")
        self.assertEqual(
            items["windowSplashScreenAnimatedIcon"], "@drawable/splash_icon_vector"
        )
        self.assertIn("android:windowSplashScreenBrandingImage", items)

    def test_ios_capabilities_follow_godot(self) -> None:
        options = {"capabilities/access_wifi": True, "capabilities/additional": ["metal"]}
        # The Mobile renderer requires an A12; Godot hides the option there.
        method = "rendering/renderer/rendering_method.mobile"
        plist = ios_plist(facts("ios", options, {method: "mobile"}))
        self.assertEqual(
            plist["UIRequiredDeviceCapabilities"],
            ["wifi", "iphone-ipad-minimum-performance-a12", "metal"],
        )
        compatibility = facts(
            "ios",
            options | {"capabilities/performance_a12": False},
            {method: "gl_compatibility"},
        )
        self.assertEqual(
            ios_plist(compatibility)["UIRequiredDeviceCapabilities"], ["wifi", "metal"]
        )

    def test_ios_launch_storyboard_replaces_the_launch_screen(self) -> None:
        self.assertIn("UILaunchScreen", ios_plist(facts("ios")))
        self.assertNotIn(
            "UILaunchScreen", ios_plist(facts("ios"), launch_storyboard=True)
        )

    def test_ios_launch_screen_color_follows_the_splash_color(self) -> None:
        def components(data: Facts) -> dict:
            return json.loads(shell_apple.launch_color(data))["colors"][0]["color"][
                "components"
            ]

        # The boot splash color, unless the storyboard sets its own.
        splash = facts(
            "ios", settings={"application/boot_splash/bg_color": [0.5, 0.25, 0.0, 1.0]}
        )
        self.assertEqual(
            components(splash),
            {"alpha": "1.000", "blue": "0.000", "green": "0.250", "red": "0.500"},
        )
        custom = facts(
            "ios",
            {
                "storyboard/use_custom_bg_color": True,
                "storyboard/custom_bg_color": [1.0, 0.0, 0.0, 1.0],
            },
        )
        self.assertEqual(components(custom)["red"], "1.000")

    def test_apple_versions_must_be_integers(self) -> None:
        with self.assertRaisesRegex(ValueError, "CFBundleShortVersionString must be"):
            ios_plist(facts("ios"), app_version="2.3.4-beta")
        plist = ios_plist(facts("ios"), app_version="2.3.4", build_number=57)
        self.assertEqual(plist["CFBundleShortVersionString"], "2.3.4")
        self.assertEqual(plist["CFBundleVersion"], "57")

    def test_additional_plist_content_must_form_a_property_list(self) -> None:
        plist = ios_plist(
            facts(
                "ios",
                {
                    "application/additional_plist_content": "<key>Extra</key>\n<string>x</string>"
                },
            )
        )
        self.assertEqual(plist["Extra"], "x")
        with self.assertRaisesRegex(ValueError, "not a property list"):
            ios_plist(
                facts("ios", {"application/additional_plist_content": "<key>A</key>"})
            )

    def test_add_on_plist_fragments_add_keys_and_conflict_on_different_values(
        self,
    ) -> None:
        # FR-021: add-ons' fragments are additive; equal values compose, different ones fail.
        base = plistlib.dumps({"CFBundleName": "Game"}).decode()
        first = plistlib.dumps({"NSCameraUsageDescription": "Scan"}).decode()
        equal = plistlib.dumps({"NSCameraUsageDescription": "Scan", "Other": 1}).decode()
        merged = plistlib.loads(shell_apple.merge_plists(base, [first, equal]).encode())
        self.assertEqual(
            merged,
            {"CFBundleName": "Game", "NSCameraUsageDescription": "Scan", "Other": 1},
        )
        different = plistlib.dumps({"NSCameraUsageDescription": "Photos"}).decode()
        with self.assertRaisesRegex(ValueError, "NSCameraUsageDescription"):
            shell_apple.merge_plists(base, [first, different])

    def test_macos_plist_names_its_icon(self) -> None:
        values = {
            "profile": PROFILE["macos"],
            "fallback_name": "Target",
            "executable": "Game",
            "bundle_id": "",
            "icon_name": "AppIcon",
            **RELEASE,
        }
        data = facts("macos", {"privacy/camera_usage_description": "Scan & play"})
        plist = plistlib.loads(shell_apple.macos_plist(data, values).encode())
        self.assertEqual(plist["CFBundleIconName"], "AppIcon")
        self.assertEqual(plist["NSCameraUsageDescription"], "Scan & play")
        self.assertEqual(plist["CFBundleExecutable"], "Game")
        plist = plistlib.loads(
            shell_apple.macos_plist(data, values | {"icon_name": ""}).encode()
        )
        self.assertNotIn("CFBundleIconName", plist)

    def test_privacy_manifest_declares_the_privacy_options(self) -> None:
        data = facts(
            "ios",
            {
                "privacy/tracking_enabled": True,
                "privacy/tracking_domains": ["tracker.example.org"],
                "privacy/user_defaults_access_reasons": 4,
                "privacy/collected_data/email_address/collected": True,
                "privacy/collected_data/email_address/collection_purposes": 3,
            },
        )
        values = {"profile": PROFILE["privacy"], "accessed_apis": True}
        privacy = plistlib.loads(shell_apple.privacy_manifest(data, values).encode())
        self.assertTrue(privacy["NSPrivacyTracking"])
        self.assertEqual(privacy["NSPrivacyTrackingDomains"], ["tracker.example.org"])
        self.assertIn(
            {
                "NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryUserDefaults",
                "NSPrivacyAccessedAPITypeReasons": ["CA92.1"],
            },
            privacy["NSPrivacyAccessedAPITypes"],
        )
        self.assertEqual(
            privacy["NSPrivacyCollectedDataTypes"][0][
                "NSPrivacyCollectedDataTypePurposes"
            ],
            [
                "NSPrivacyCollectedDataTypePurposeAnalytics",
                "NSPrivacyCollectedDataTypePurposeAppFunctionality",
            ],
        )
        # Godot's macOS export declares no required-reason APIs.
        privacy = plistlib.loads(
            shell_apple.privacy_manifest(data, values | {"accessed_apis": False}).encode()
        )
        self.assertEqual(privacy["NSPrivacyAccessedAPITypes"], [])

    def test_localizations_need_project_translations(self) -> None:
        values = {"profile": PROFILE["ios"], "fallback_name": "Target"}
        self.assertEqual(shell_apple.localizations(facts("ios"), values, False), {})
        data = facts(
            "ios",
            {"privacy/camera_usage_description_localized": {"de": "Kamera"}},
            {"application/config/name": "Game"},
        )
        data.name_translations = {"en": None, "de": 'Spiel & "Co"', "fr": None}
        tables = shell_apple.localizations(data, values, False)
        self.assertEqual(tables["en"]["CFBundleDisplayName"], "Game")
        self.assertEqual(
            tables["de"],
            {"CFBundleDisplayName": 'Spiel & "Co"', "NSCameraUsageDescription": "Kamera"},
        )
        self.assertEqual(tables["fr"], {})
        catalog = json.loads(shell_apple.string_catalog(tables))
        self.assertEqual(
            catalog["strings"]["CFBundleDisplayName"]["localizations"]["de"],
            {"stringUnit": {"state": "translated", "value": 'Spiel & "Co"'}},
        )
        shell_apple.write_strings(tables, self.root / "strings")
        self.assertIn(
            'CFBundleDisplayName = "Spiel & \\"Co\\"";',
            (self.root / "strings/de.lproj/InfoPlist.strings").read_text(),
        )

    def test_templates_and_values_must_match(self) -> None:
        with self.assertRaisesRegex(ValueError, "themes.xml.tpl has the placeholders"):
            fill("themes.xml.tpl", {"MAIN_ITEMS": ""})
        # An empty block removes its line; braces of values stay as they are.
        text = fill("themes.xml.tpl", {"MAIN_ITEMS": "", "SPLASH_ITEMS": "{MAIN_ITEMS}"})
        self.assertNotIn("{SPLASH_ITEMS}", text)
        self.assertIn("{MAIN_ITEMS}", text)


if __name__ == "__main__":
    unittest.main()
