"""Write the shell files of an Android application as Godot's Android exporter does."""

import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from tools.platforms.shell_common import (
    Facts,
    color_html,
    fill,
    release_value,
    set_off,
    xml,
)
from tools.platforms.shell_overrides import defined_styles, without_styles

ANDROID_NAMESPACE = "http://schemas.android.com/apk/res/android"
TOOLS_NAMESPACE = "http://schemas.android.com/tools"
ANDROID = "{" + ANDROID_NAMESPACE + "}"
PERMISSION_TAGS = ("uses-permission", "uses-permission-sdk-23")


def _bool(value: object) -> str:
    return "true" if value else "false"


def declared_permissions(facts: Facts) -> list[str]:
    """The permissions Godot's permissions/* export options declare."""
    names = [
        "android.permission." + key.removeprefix("permissions/").upper()
        for key, value in sorted(facts.options.items())
        if key.startswith("permissions/")
        and key != "permissions/custom_permissions"
        and value is True
    ]
    for name in facts.option("permissions/custom_permissions"):
        name = name.strip()
        if name and name not in names:
            names.append(name)
    return names


def max_sdk_versions(declared: list[str], profile: Mapping[str, Any]) -> dict[str, str]:
    """The android:maxSdkVersion Godot's exporter gives declared permissions."""
    return {
        name: limit["max_sdk"]
        for name, limit in profile["max_sdk_permissions"].items()
        if name in declared and limit.get("requires", name) in declared
    }


def permission_entries(declared: list[str], max_sdk: Mapping[str, str]) -> list[str]:
    """
    The uses-permission elements of the permissions Godot's export options declare.

    max_sdk limits them as Godot's exporter does. Library permissions are not listed:
    the manifest merger merges them below these, with its tools: markers.
    """
    return [
        f'    <uses-permission android:name="{xml(name)}"'
        + (f' android:maxSdkVersion="{xml(max_sdk[name])}"' if name in max_sdk else "")
        + " />"
        for name in declared
    ]


def manifest(facts: Facts, values: Mapping[str, Any]) -> str:
    """The manifest Godot's Android exporter writes."""
    profile = values["profile"]
    code = int(release_value(facts, values, "version/code", values["build_number"]))
    if not 1 <= code <= profile["max_version_code"]:
        raise ValueError(
            f"Android versionCode must be from 1 to {profile['max_version_code']}, "
            f"got {code}"
        )
    categories = profile["app_categories"]
    category = facts.option("package/app_category")
    if not 0 <= category <= len(categories):
        raise ValueError(
            f"package/app_category must be from 0 to {len(categories)}, got {category}"
        )
    declared = declared_permissions(facts)
    method = str(facts.setting("rendering/renderer/rendering_method"))
    vulkan = profile["vulkan"]
    features = []
    if (
        method in vulkan["rendering_methods"]
        and facts.setting("rendering/rendering_device/driver.android") == vulkan["driver"]
    ):
        # Request Vulkan; require it only without the OpenGL fallback.
        required = not facts.setting("rendering/rendering_device/fallback_to_opengl3")
        features = [
            "    <uses-feature",
            '        android:name="android.hardware.vulkan.level"',
            '        android:required="false"',
            '        android:version="1" />',
            "",
            "    <uses-feature",
            '        android:name="android.hardware.vulkan.version"',
            f'        android:required="{_bool(required)}"',
            f'        android:version="{vulkan["version"]}" />',
        ]
    name = facts.text("package/name") or facts.setting("application/config/name")
    short_version = release_value(facts, values, "version/name", values["app_version"])
    screens = {
        f"{size.upper()}_SCREENS": _bool(facts.option("screen/support_" + size))
        for size in profile["screen_sizes"]
    }
    return fill(
        "AndroidManifest.xml.tpl",
        screens
        | {
            "VERSION_CODE": str(code),
            "VERSION_NAME": xml(short_version),
            "MIN_SDK_VERSION": xml(
                facts.text("gradle_build/min_sdk") or profile["min_sdk"]
            ),
            "TARGET_SDK_VERSION": xml(
                facts.text("gradle_build/target_sdk") or profile["target_sdk"]
            ),
            "PERMISSIONS": set_off(
                permission_entries(declared, max_sdk_versions(declared, profile))
            ),
            "VULKAN_FEATURES": set_off(features),
            "APP_NAME": xml(name or values["fallback_name"]),
            "ALLOW_BACKUP": _bool(facts.option("user_data_backup/allow")),
            "APP_CATEGORY": (
                f'        android:appCategory="{categories[category]}"'
                if category < len(categories)
                else ""
            ),
            "EXTRACT_NATIVE_LIBS": _bool(
                facts.option("gradle_build/compress_native_libraries")
            ),
            "HAS_FRAGILE_USER_DATA": _bool(
                facts.option("package/retain_data_on_uninstall")
            ),
            "IS_GAME": _bool(category == profile["game_category"]),
            "REQUEST_LEGACY_EXTERNAL_STORAGE": _bool(
                any(name in declared for name in profile["storage_permissions"])
            ),
            "EDITOR_VERSION": xml(values["editor_version"]),
            # Debuggable builds register the plugin that passes bazel run's arguments.
            "LAUNCH_ARGUMENTS_PLUGIN": (
                "        <meta-data\n"
                '            android:name="org.godotengine.plugin.v2.RulesGodotLaunchArguments"\n'
                '            android:value="com.godot.game.LaunchArgumentsPlugin" />\n'
                if values.get("launch_arguments")
                else ""
            ),
            "RENDERING_METHOD": xml(
                facts.setting("rendering/renderer/rendering_method.mobile") or method
            ),
            "EXCLUDE_FROM_RECENTS": _bool(facts.option("package/exclude_from_recents")),
            "RESIZEABLE": _bool(facts.setting("display/window/size/resizable")),
            "ORIENTATION": facts.orientation(profile["orientations"]),
            "CONFIG_CHANGES": "|".join(profile["config_changes"]),
            "LAUNCHER_CATEGORIES": "\n".join(
                f'                <category android:name="android.intent.category.{name}" />'
                for option, name in profile["launcher_categories"]
                if facts.option(option)
            ),
        },
    )


def _transparent(facts: Facts) -> bool:
    return bool(facts.setting("display/window/per_pixel_transparency/allowed"))


def command_line(facts: Facts, values: Mapping[str, Any]) -> list[str]:
    """Godot's command line flags of its Android export."""
    flags = values["profile"]["command_line"]
    if facts.option("xr_features/xr_mode") != 0:
        raise ValueError(
            "XR exports (xr_features/xr_mode) are not supported by rules_godot"
        )
    args = [arg for arg in facts.text("command_line/extra_args").split(" ") if arg]
    args += flags["xr_off"]
    args += [flag for option, flag in flags["flags"] if facts.option(option)]
    # As Godot's Gradle export, whose themes this shell writes: with transparency the
    # system bars' fallback color is transparent too.
    background = (
        "#00000000"
        if _transparent(facts)
        else "#" + color_html(facts.option("screen/background_color"))
    )
    args += [flags["background_color"], background]
    args += [flag for option, flag in flags["late_flags"] if facts.option(option)]
    return ["--main-pack", "res://main.pck", *args]


def command_line_file(facts: Facts, values: Mapping[str, Any]) -> bytes:
    """
    The assets/_cl_ file of Godot's Android export, which Godot's activity reads.

    Godot encodes the argument count, then each argument's byte length and UTF-8
    bytes, as little-endian 32-bit integers.
    """
    args = [arg.encode("utf-8") for arg in command_line(facts, values)]
    return struct.pack("<I", len(args)) + b"".join(
        struct.pack("<I", len(arg)) + arg for arg in args
    )


def parse_command_line_file(data: bytes) -> list[str]:
    """The arguments of an assets/_cl_ file, as Godot's CommandLineFileParser reads them."""
    (count,) = struct.unpack_from("<I", data)
    offset, args = 4, []
    for _ in range(count):
        (length,) = struct.unpack_from("<I", data, offset)
        args.append(data[offset + 4 : offset + 4 + length].decode("utf-8"))
        offset += 4 + length
    if offset != len(data):
        raise ValueError(f"{len(data) - offset} bytes follow the last argument")
    return args


def themes(
    facts: Facts, values: Mapping[str, Any], overrides: Sequence[Path] = ()
) -> str:
    """
    The splash screen and main themes Godot's Android export writes.

    A style that the application's unqualified value resources (overrides) define
    replaces the shell's style of that name as a whole, so the shell leaves it out.
    """
    translucent = _transparent(facts)
    main = {
        "android:windowSwipeToDismiss": _bool(facts.option("gesture/swipe_to_dismiss")),
        "android:windowIsTranslucent": _bool(translucent),
        "android:windowBackground": (
            "@android:color/transparent"
            if translucent
            else "#" + color_html(facts.option("screen/background_color"))
        ),
    }
    background = facts.option("splash_screen/background_color")
    splash = {
        "android:windowSplashScreenBackground": (
            "@mipmap/icon_background"
            if background == [0.0, 0.0, 0.0, 1.0]
            else "#" + color_html(background)
        ),
        "windowSplashScreenAnimatedIcon": (
            "@drawable/splash_icon_vector"
            if facts.text("splash_screen/icon").endswith(".xml")
            else "@drawable/splash_icon"
        ),
    }
    if facts.text("splash_screen/branding_image"):
        splash["android:windowSplashScreenBrandingImage"] = (
            "@drawable/splash_branding_image"
        )
    # Custom attributes extend the main theme, or with a [splash] prefix the splash
    # theme. As in Godot's export they keep the main theme's attributes, may replace
    # the splash screen's and never its link to the main theme or its translucency.
    for key, value in facts.option("gradle_build/custom_theme_attributes").items():
        if key.startswith("[splash]"):
            splash[key.removeprefix("[splash]")] = str(value)
        elif key not in main:
            main[key] = str(value)
    splash["postSplashScreenTheme"] = "@style/GodotAppMainTheme"
    splash["android:windowIsTranslucent"] = _bool(translucent)

    def items(attributes: dict[str, str]) -> str:
        return "\n".join(
            f'        <item name="{xml(name)}">{xml(value)}</item>'
            for name, value in attributes.items()
        )

    text = fill(
        "themes.xml.tpl", {"MAIN_ITEMS": items(main), "SPLASH_ITEMS": items(splash)}
    )
    return without_styles(text, defined_styles(overrides))


def main_manifest(shell_text: str, consumer: Path, owned: Mapping[str, str]) -> str:
    """
    The application's own manifest as the main manifest of the manifest merge.

    The shell manifest (shell_text) merges below it as a library manifest, so the
    application's attributes and tools: markers apply to the shell's elements.
    The shell's permissions, those Godot's export options declare, are added here, so
    that like the application's own they rank above every library's and a library's
    tools:node="remove" cannot drop them; those the application declares itself,
    including those it removes with tools:node="remove", stay as it wrote them. The
    shell's <manifest>
    attributes and SDK versions fill what the application leaves out; values
    rules_godot owns must not be set.
    """
    shell = ElementTree.fromstring(shell_text)
    ElementTree.register_namespace("android", ANDROID_NAMESPACE)
    ElementTree.register_namespace("tools", TOOLS_NAMESPACE)
    parser = ElementTree.XMLParser(target=ElementTree.TreeBuilder(insert_comments=True))
    root = ElementTree.parse(consumer, parser).getroot()
    if root.tag != "manifest":
        raise ValueError(f"{consumer} is not an Android manifest")
    for element in [root, *root.findall("uses-sdk")]:
        for attribute in element.attrib:
            name = attribute.removeprefix(ANDROID)
            if attribute.startswith(ANDROID) and name in owned:
                raise ValueError(
                    f"{consumer} sets android:{name} on <{element.tag}>, which belongs "
                    f"to {owned[name]}; set it there instead"
                )
    for attribute, value in shell.attrib.items():
        if attribute.startswith(ANDROID):
            root.attrib.setdefault(attribute, value)
    shell_sdk = shell.find("uses-sdk")
    assert shell_sdk is not None
    declared = {
        (element.tag, element.get(ANDROID + "name"))
        for element in root
        if element.tag in PERMISSION_TAGS
    }
    added = [
        element
        for element in shell
        if element.tag in PERMISSION_TAGS
        and (element.tag, element.get(ANDROID + "name")) not in declared
    ]
    sdk = root.find("uses-sdk")
    if sdk is None:
        added.insert(0, shell_sdk)
    else:
        sdk.attrib.update(shell_sdk.attrib)
    for index, element in enumerate(added):
        root.insert(index, element)
    ElementTree.indent(root, space="    ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        + ElementTree.tostring(root, encoding="unicode")
        + "\n"
    )
