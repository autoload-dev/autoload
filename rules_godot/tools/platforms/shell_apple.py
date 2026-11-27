"""
Write the shell files of iOS and macOS applications as Godot's Apple exporters do.

Sections: Plist merging, Info plists, Localization.
"""

import json
import plistlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from tools.platforms.shell_common import Facts, fill, release_value, xml

# ==== Plist merging ===========================================================


class _UniqueKeys(dict):
    def __setitem__(self, key: str, value: Any) -> None:
        if key in self:
            raise ValueError(f"Duplicate plist key: {key}")
        super().__setitem__(key, value)


# The elements of the XML property list format.
_PLIST_ELEMENTS = {
    "plist",
    "dict",
    "array",
    "key",
    "string",
    "integer",
    "real",
    "true",
    "false",
    "date",
    "data",
}


def _alternates_keys_and_values(children: list[ElementTree.Element]) -> bool:
    """Whether a dictionary's children are keys, each followed by its value."""
    return len(children) % 2 == 0 and all(
        child.tag == "key" if i % 2 == 0 else child.tag not in {"key", "plist"}
        for i, child in enumerate(children)
    )


def _element_error(element: ElementTree.Element, root: ElementTree.Element) -> str | None:
    """Return why the element breaks the structure of a plist, or None."""
    children = list(element)
    tags = [child.tag for child in children]
    if element.tag == "plist":
        top_level = element is root and tags == ["dict"]
        return None if top_level else "Expected one top-level plist dictionary"
    if element.tag == "dict":
        pairs = _alternates_keys_and_values(children)
        return None if pairs else "Malformed plist dictionary key/value sequence"
    if element.tag == "array":
        return "Malformed plist array" if {"key", "plist"} & set(tags) else None
    if children:
        return f"Unexpected child in plist scalar {element.tag}"
    if element.tag in {"true", "false"} and (element.text or "").strip():
        return "A plist boolean cannot contain text"
    return None


def _strict_plist(text: str) -> dict[str, Any]:
    root = ElementTree.fromstring(text)
    unknown = {element.tag for element in root.iter()} - _PLIST_ELEMENTS
    if unknown:
        raise ValueError(f"Unknown plist XML elements: {sorted(unknown)}")
    for element in root.iter():
        error = _element_error(element, root)
        if error:
            raise ValueError(error)
    if root.tag != "plist":
        raise ValueError("Expected a plist root")
    return plistlib.loads(text.encode("utf-8"), dict_type=_UniqueKeys)


def _merge(
    values: dict[str, Any], extra: dict[str, Any], overrides: bool = False
) -> None:
    for key, value in extra.items():
        if overrides and key in {"UIRequiresFullScreen", "UIStatusBarHidden"}:
            if type(value) is not bool:
                raise ValueError(f"{key} must be a plist boolean")
        elif key in values and plistlib.dumps(values[key]) != plistlib.dumps(value):
            raise ValueError(
                f"Additional plist content conflicts with generated or library key {key}"
            )
        values[key] = value


def merge_plists(base: str, fragments: list[str]) -> str:
    """Merge declared library dictionaries without order-dependent replacement."""
    values = dict(_strict_plist(base))
    for fragment in fragments:
        _merge(values, _strict_plist(fragment))
    return plistlib.dumps(values, sort_keys=True).decode("utf-8")


# ==== Info plists =============================================================


def _plist_bool(value: object) -> str:
    return "<true/>" if value else "<false/>"


def _plist_strings(values: list[str], indent: str = "    ") -> str:
    """A plist array of strings as the value of a dict entry at indent."""
    if not values:
        return "<array/>"
    items = "".join(f"{indent}    <string>{xml(value)}</string>\n" for value in values)
    return f"<array>\n{items}{indent}</array>"


def _checked(
    text: str, name: str, additional: str = "", owned: Mapping[str, Any] | None = None
) -> str:
    """Parse strictly and merge permitted extra dictionary entries exactly once."""
    try:
        values = dict(_strict_plist(text))
        _merge(values, dict(owned or {}))
        if additional.strip():
            fragment = _strict_plist(
                fill("plist_fragment.plist.tpl", {"ENTRIES": additional})
            )
            _merge(values, fragment, overrides=True)
        if additional.strip() or owned:
            return plistlib.dumps(values, sort_keys=True).decode("utf-8")
    except Exception as error:
        raise ValueError(
            f"The generated {name} is not a property list: {error}"
        ) from error
    return text


def _apple_version(value: str, key: str) -> str:
    # App Store Connect accepts one to three period-separated integers.
    parts = value.split(".")
    if len(parts) > 3 or not all(part.isdigit() for part in parts):
        raise ValueError(
            f"{key} must be one to three period-separated integers, got {value!r}"
        )
    return value


def _versions(facts: Facts, values: Mapping[str, Any]) -> tuple[str, str]:
    short = release_value(
        facts, values, "application/short_version", values["app_version"]
    )
    bundle = release_value(facts, values, "application/version", values["build_number"])
    return str(short), str(bundle)


def _usage_descriptions(facts: Facts, table: list, keep_empty: bool) -> str:
    """The usage descriptions of the privacy/*_usage_description options."""
    return "\n".join(
        f"    <key>{key}</key>\n    <string>{xml(facts.text(option))}</string>"
        for option, key in table
        if keep_empty or facts.text(option)
    )


def _name(facts: Facts, values: Mapping[str, Any]) -> str:
    return str(facts.setting("application/config/name") or values["fallback_name"])


# The launch screen of Godot's iOS export: the splash image on the launch color.
_LAUNCH_SCREEN = """    <key>UILaunchScreen</key>
    <dict>
        <key>UIColorName</key>
        <string>LaunchScreenBackground</string>
        <key>UIImageName</key>
        <string>SplashImage</string>
    </dict>"""


def ios_plist(facts: Facts, values: Mapping[str, Any]) -> str:
    """The Info.plist Godot's iOS exporter writes."""
    profile = values["profile"]
    short, bundle = _versions(facts, values)
    capabilities = [
        name for option, name in profile["capabilities"] if facts.option(option)
    ]
    a12 = profile["a12"]
    method = facts.setting("rendering/renderer/rendering_method.mobile")
    if method in a12["rendering_methods"] or facts.option(a12["option"]):
        capabilities.append(a12["capability"])
    capabilities += facts.option("capabilities/additional")
    return _checked(
        fill(
            "Godot.plist.tpl",
            {
                "DISPLAY_NAME": xml(_name(facts, values)),
                "SHORT_VERSION": _apple_version(short, "CFBundleShortVersionString"),
                "BUNDLE_VERSION": _apple_version(bundle, "CFBundleVersion"),
                "DOCS_IN_PLACE": _plist_bool(
                    facts.option("user_data/accessible_from_files_app")
                ),
                "DOCS_SHARING": _plist_bool(
                    facts.option("user_data/accessible_from_itunes_sharing")
                ),
                "CAPABILITIES": _plist_strings(capabilities),
                # Godot's iOS export writes every usage description, its
                # macOS export only those with a text.
                "USAGE_DESCRIPTIONS": _usage_descriptions(
                    facts, profile["usage_descriptions"], keep_empty=True
                ),
                "ORIENTATIONS": _plist_strings(
                    facts.orientation(profile["orientations"])
                ),
                "IPAD_ORIENTATIONS": _plist_strings(
                    facts.orientation(profile["ipad_orientations"])
                ),
                # The application's own launch storyboard replaces the launch screen.
                "LAUNCH_SCREEN": ""
                if values.get("launch_storyboard")
                else _LAUNCH_SCREEN,
            },
        ),
        "Info.plist",
        facts.text("application/additional_plist_content"),
        owned=values.get("bundle_keys"),
    )


def macos_plist(facts: Facts, values: Mapping[str, Any]) -> str:
    """The Info.plist Godot's macOS exporter writes."""
    short, bundle = _versions(facts, values)
    icon_name = values["icon_name"]
    return _checked(
        fill(
            "macos_Info.plist.tpl",
            {
                "EXECUTABLE": xml(values["executable"]),
                "DISPLAY_NAME": xml(_name(facts, values)),
                "ICON_NAME": (
                    f"    <key>CFBundleIconName</key>\n    <string>{xml(icon_name)}</string>"
                    if icon_name
                    else ""
                ),
                "BUNDLE_ID": xml(
                    values["bundle_id"]
                    or facts.text("application/bundle_identifier")
                    or "org.godotengine.game"
                ),
                "SHORT_VERSION": xml(short),
                "SIGNATURE": xml(facts.text("application/signature")),
                "BUNDLE_VERSION": xml(bundle),
                "USAGE_DESCRIPTIONS": _usage_descriptions(
                    facts, values["profile"]["usage_descriptions"], keep_empty=False
                ),
                "COPYRIGHT": xml(facts.text("application/copyright")),
                "APP_CATEGORY": xml(facts.text("application/app_category").lower()),
                "MIN_VERSION_ARM64": xml(
                    facts.text("application/min_macos_version_arm64")
                ),
                "MIN_VERSION_X86_64": xml(
                    facts.text("application/min_macos_version_x86_64")
                ),
                "HIGH_RES": _plist_bool(facts.option("display/high_res")),
            },
        ),
        "Info.plist",
        facts.text("application/additional_plist_content"),
    )


def _flagged(flags: int, choices: list[str]) -> list[str]:
    """Return the choices whose bits are set in the flags."""
    return [choice for bit, choice in enumerate(choices) if flags & (1 << bit)]


def _accessed_api_types(facts: Facts, accessed_apis: list) -> list[str]:
    """Return the manifest's entries of the required-reason APIs the options declare."""
    entries = []
    for name, category, reasons in accessed_apis:
        flags = facts.option(f"privacy/{name}_access_reasons")
        if flags:
            entries.append(
                "        <dict>\n"
                "            <key>NSPrivacyAccessedAPIType</key>\n"
                f"            <string>NSPrivacyAccessedAPICategory{category}</string>\n"
                "            <key>NSPrivacyAccessedAPITypeReasons</key>\n"
                f"            {_plist_strings(_flagged(flags, reasons), ' ' * 12)}\n"
                "        </dict>\n"
            )
    return entries


def _collected_data_types(facts: Facts, privacy: Mapping[str, Any]) -> list[str]:
    """Return the manifest's entries of the data types the options declare collected."""
    entries = []
    for name, data_type in privacy["collected_data"]:
        prefix = f"privacy/collected_data/{name}/"
        if not facts.option(prefix + "collected"):
            continue
        purposes = _flagged(
            facts.option(prefix + "collection_purposes"),
            [
                "NSPrivacyCollectedDataTypePurpose" + purpose
                for purpose in privacy["purposes"]
            ],
        )
        entries.append(
            "        <dict>\n"
            "            <key>NSPrivacyCollectedDataType</key>\n"
            f"            <string>NSPrivacyCollectedDataType{data_type}</string>\n"
            "            <key>NSPrivacyCollectedDataTypeLinked</key>\n"
            f"            {_plist_bool(facts.option(prefix + 'linked_to_user'))}\n"
            "            <key>NSPrivacyCollectedDataTypePurposes</key>\n"
            f"            {_plist_strings(purposes, ' ' * 12)}\n"
            "            <key>NSPrivacyCollectedDataTypeTracking</key>\n"
            f"            {_plist_bool(facts.option(prefix + 'used_for_tracking'))}\n"
            "        </dict>\n"
        )
    return entries


def _plist_array(entries: list[str]) -> str:
    return f"<array>\n{''.join(entries)}    </array>" if entries else "<array/>"


def privacy_manifest(facts: Facts, values: Mapping[str, Any]) -> str:
    """The privacy manifest Godot's Apple exporters write from the privacy/* options."""
    privacy = values["profile"]
    accessed_apis = privacy["accessed_apis"] if values["accessed_apis"] else []
    return _checked(
        fill(
            "PrivacyInfo.xcprivacy.tpl",
            {
                "ACCESSED_API_TYPES": _plist_array(
                    _accessed_api_types(facts, accessed_apis)
                ),
                "COLLECTED_DATA_TYPES": _plist_array(
                    _collected_data_types(facts, privacy)
                ),
                "TRACKING": _plist_bool(facts.option("privacy/tracking_enabled")),
                "TRACKING_DOMAINS": _plist_strings(
                    facts.option("privacy/tracking_domains")
                ),
            },
        ),
        "privacy manifest",
    )


# ==== Localization ============================================================


def localizations(
    facts: Facts, values: Mapping[str, Any], macos: bool
) -> dict[str, dict[str, str]]:
    """
    Return the localized Info.plist values by locale, as Godot's Apple exporters do.

    Godot localizes only a project with translations: English with the base
    values, every other locale with its translated name and the values its
    *_localized options have.
    """
    if not facts.name_translations:
        return {}
    usage = values["profile"]["usage_descriptions"]
    localized = (
        [*usage, ["application/copyright", "NSHumanReadableCopyright"]]
        if macos
        else usage
    )
    tables = {"en": {"CFBundleDisplayName": _name(facts, values)}}
    tables["en"] |= {
        key: facts.text(option)
        for option, key in localized
        if not macos or facts.text(option) or key == "NSHumanReadableCopyright"
    }
    for locale, name in facts.name_translations.items():
        if locale == "en":
            continue
        tables[locale] = {"CFBundleDisplayName": name} if name else {}
        tables[locale] |= {
            key: facts.option(option + "_localized")[locale]
            for option, key in localized
            if locale in facts.option(option + "_localized")
        }
    return tables


def _strings_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def write_strings(tables: dict[str, dict[str, str]], directory: Path) -> None:
    """Write each locale's values as <locale>.lproj/InfoPlist.strings of directory."""
    directory.mkdir(parents=True, exist_ok=True)
    for locale, entries in tables.items():
        (directory / (locale + ".lproj")).mkdir()
        (directory / (locale + ".lproj") / "InfoPlist.strings").write_text(
            "/* Localized versions of Info.plist keys */\n\n"
            + "".join(
                f'{key} = "{_strings_value(value)}";\n' for key, value in entries.items()
            ),
            encoding="utf-8",
        )


def string_catalog(tables: dict[str, dict[str, str]]) -> str:
    """Return the values as an InfoPlist string catalog, which Xcode compiles by locale."""
    strings: dict[str, Any] = {}
    for locale, entries in tables.items():
        for key, value in entries.items():
            unit = {"stringUnit": {"state": "translated", "value": value}}
            strings.setdefault(key, {"localizations": {}})["localizations"][locale] = unit
    catalog = {"sourceLanguage": "en", "strings": strings, "version": "1.0"}
    return json.dumps(catalog, indent=2, sort_keys=True) + "\n"


def launch_color(facts: Facts) -> str:
    """The asset catalog color set of the launch screen, as Godot's storyboard colors it."""
    color = (
        facts.option("storyboard/custom_bg_color")
        if facts.option("storyboard/use_custom_bg_color")
        else facts.setting("application/boot_splash/bg_color")
    )
    red, green, blue, alpha = [*color, 1.0][:4]
    components = {
        "alpha": f"{alpha:.3f}",
        "blue": f"{blue:.3f}",
        "green": f"{green:.3f}",
        "red": f"{red:.3f}",
    }
    contents = {
        "colors": [
            {
                "color": {"color-space": "srgb", "components": components},
                "idiom": "universal",
            }
        ],
        "info": {"author": "xcode", "version": 1},
    }
    return json.dumps(contents, indent=2) + "\n"
