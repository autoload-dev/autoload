"""
The project settings that name files, per Godot minor, how rules_godot classifies them, and
the sections of Godot's own settings.

Godot reports which settings name a file or directory (their property hint); the check
//godot/private/engine/setting_kinds:setting_kinds_match_godot_test compares this table with
that report. rules_godot adds what Godot does not report: the sections and arrays whose values
are paths, and per setting the configurations that carry it (purposes) and, for the export
configuration, whether Godot's export loads the file itself whatever the pack contains
(context) or the file is part of the game the configuration starts (content).

A key outside Godot's sections, such as an add-on's own key, is unknown to the table: it is
program-level and content-bound, so no import carries it, and a path it declares is checked
like a content-bound file.
"""

load("//godot/private:versions.bzl", "require_supported_source_version")

visibility(["//godot/..."])

_CARRIED = ["export", "runtime", "editor"]

def _kind(shape, hint, binding, purposes = _CARRIED):
    """
    One classified setting.

    Args:
        shape: path, path_list, path_map, autoload, shader_global or directory.
        hint: Godot's property hint for the key (file or dir); None for a section or array
            Godot does not hint, which the check skips.
        binding: context or content for the export configuration; None when export does not
            carry it.
        purposes: The purposes whose configuration carries the setting.

    Returns:
        The row as a dict, which JSON encodes.
    """
    return {"binding": binding, "hint": hint, "purposes": purposes, "shape": shape}

# Godot 4.7; Godot 4.8 reports the same keys.
_GODOT_4_7 = {
    # The export renders or copies these images itself.
    "application/boot_splash/image": _kind("path", "file", "context"),
    "application/config/icon": _kind("path", "file", "context"),
    "application/config/macos_native_icon": _kind("path", "file", "context"),
    "application/config/windows_native_icon": _kind("path", "file", "context"),
    # Roots of the export's selection.
    "application/run/main_scene": _kind("path", "file", "content"),
    "autoload/*": _kind("autoload", None, "content"),
    # Files of the game the configuration starts.
    "audio/buses/default_bus_layout": _kind("path", "file", "content"),
    "display/mouse_cursor/custom_image": _kind("path", "file", "content"),
    "gui/theme/custom": _kind("path", "file", "content"),
    "gui/theme/custom_font": _kind("path", "file", "content"),
    "internationalization/locale/translation_remaps": _kind("path_map", None, "content"),
    "internationalization/locale/translations": _kind("path_list", None, "content"),
    "network/tls/certificate_bundle_override": _kind("path", "file", "content"),
    "rendering/environment/defaults/default_environment": _kind("path", "file", "content"),
    "rendering/vrs/texture": _kind("path", "file", "content"),
    "shader_globals/*": _kind("shader_global", None, "content"),
    "xr/openxr/default_action_map": _kind("path", "file", "content"),
    # The editor's script templates.
    "editor/script/templates_search_path": _kind("directory", "dir", None, ["editor"]),
}

SETTING_KIND_TABLES = {
    "4.7": _GODOT_4_7,
    "4.8": _GODOT_4_7,
}

# The sections of Godot's own settings: registered, those Godot registers at startup, which
# the check compares, and read, those it reads from project.godot without registering them.
_GODOT_4_7_SECTIONS = {
    "registered": [
        "accessibility",
        "animation",
        "application",
        "audio",
        "collada",
        "compression",
        "debug",
        "display",
        "editor",
        "filesystem",
        "gui",
        "input",
        "input_devices",
        "internationalization",
        "layer_names",
        "memory",
        "navigation",
        "network",
        "physics",
        "rendering",
        "threading",
        "xr",
    ],
    # dotnet is registered only by Godot's .NET builds.
    "read": ["autoload", "dotnet", "editor_plugins", "importer_defaults", "shader_globals"],
}

ENGINE_SECTION_TABLES = {
    "4.7": _GODOT_4_7_SECTIONS,
    "4.8": _GODOT_4_7_SECTIONS,
}

def setting_kinds(version):
    """
    Return the classified file-referencing project settings of an engine version.

    Args:
        version: Canonical engine version, such as 4.7.2, 4.8.0-beta1 or a source's 4.7.3-rc.

    Returns:
        A dict of setting key (a section's keys as section/*) to its kind.
    """
    return SETTING_KIND_TABLES[_series(version)]

def engine_sections(version):
    """
    Return the sections of Godot's own settings of an engine version.

    Args:
        version: Canonical engine version, as for setting_kinds.

    Returns:
        A sorted list of section names; a key in any other section is unknown to Godot.
    """
    sections = ENGINE_SECTION_TABLES[_series(version)]
    return sorted(sections["registered"] + sections["read"])

def _series(version):
    require_supported_source_version(version)
    series = ".".join(version.split("-")[0].split(".")[:2])
    if series not in SETTING_KIND_TABLES:
        fail("rules_godot has no setting kinds for Godot %s" % series)
    return series
