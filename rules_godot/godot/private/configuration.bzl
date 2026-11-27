"""Explicit project contributions with predictable conflict handling."""

visibility("private")

_IDENTIFIER_START = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
_DIGITS = "0123456789"

def merge_configuration(destination, additions, origins, owner, overrides = {}):
    """
    Combine equal contributions; require an explicit consumer override.

    Args:
        destination: Mutable configuration key-to-value dictionary.
        additions: New key-to-value contributions.
        origins: Mutable configuration key-to-declaring-label dictionary.
        owner: Origin of the new contributions.
        overrides: Keys explicitly overridden by the final consumer.
    """
    for key, value in additions.items():
        if key in overrides:
            continue
        if key in destination and destination[key] != value:
            fail((
                "Conflicting Godot configuration %r from %s (%r) and %s (%r); " +
                "declare an explicit override"
            ) % (key, origins[key], destination[key], owner, value))
        destination[key] = value
        if key not in origins:
            origins[key] = owner

# Characters that would end a key in project.godot or export_presets.cfg.
_KEY_DELIMITERS = ["\n", "\r", "=", "[", "]", '"']

# The settings the ruleset fixes in the configuration of imports and exports, replacing the
# authored ones and their feature overrides. Godot imports a VRAM-compressed texture in each
# format family whose setting is true and, whatever the settings, in the family the
# editor's CPU prefers: S3TC/BPTC on macOS and x86_64, ETC2/ASTC on arm64 Linux. With both
# true, every execution platform imports the same variants and every export platform finds
# its own; a pack keeps only the variants of its feature tags.
PINNED_SETTINGS = {
    "rendering/textures/vram_compression/import_etc2_astc": "true",
    "rendering/textures/vram_compression/import_s3tc_bptc": "true",
}

def validate_settings(settings, main_scene_overrides = True):
    """
    Validate the keys of explicitly encoded Godot literal settings.

    Args:
        settings: Dictionary of section/property names to literal strings.
        main_scene_overrides: Whether feature overrides of the main scene, such as
            application/run/main_scene.<tag>, are allowed: they are where a view checks
            the scene they name against its members, which a pack's own settings bypass.
    """
    for key, value in settings.items():
        if not _is_setting_key(key):
            fail("Expected section/property Godot setting key, got %r" % key)
        if _names_a_relationship(key, main_scene_overrides):
            fail((
                "Use autoloads, main_scene and the editor parts of add-ons instead of " +
                "the setting %s"
            ) % key)
        if not value.strip():
            fail("Expected an explicit Godot literal string for setting %s" % key)
        _check_pinned(key, value)

def _is_setting_key(key):
    """Whether key has the section/property form and no character that would end it."""
    if key.strip("/") != key or "/" not in key:
        return False
    return not any([c in key for c in _KEY_DELIMITERS])

_MAIN_SCENE = "application/run/main_scene"

def _names_a_relationship(key, main_scene_overrides):
    """Whether key sets an autoload, an editor plugin or the main scene; see validate_settings."""
    if key.startswith(("autoload/", "editor_plugins/")):
        return True
    if key.split(".")[0] != _MAIN_SCENE:
        return False
    return key == _MAIN_SCENE or not main_scene_overrides

def _check_pinned(key, value):
    """Fail for a setting, or a feature override of one, against PINNED_SETTINGS."""
    pinned = PINNED_SETTINGS.get(key.split(".")[0])
    if pinned != None and value.strip() != pinned:
        fail((
            "rules_godot imports every VRAM-compressed texture in both S3TC/BPTC and " +
            "ETC2/ASTC, so imports agree on every execution platform and each export " +
            "keeps the formats its platform needs; remove the setting %s"
        ) % key)

def validate_export_options(options):
    """
    Validate the keys of explicitly encoded export preset options.

    Args:
        options: Dictionary of export option names to literal strings.
    """
    for key, value in options.items():
        if not key or any([c in key for c in _KEY_DELIMITERS + [" "]]):
            fail("Expected an export option name, got %r" % key)
        if key in _PRESET_FIELDS:
            fail("%s belongs to preset_settings" % key)
        if not value.strip():
            fail("Expected an explicit Godot literal string for export option %s" % key)

_PRESET_FIELDS = ["script_export_mode"]

def validate_preset_settings(settings):
    """
    Validate the supported preset namespace without manufacturing omitted defaults.

    Custom features are no preset field: the project's custom-feature build settings
    give them.

    Args:
        settings: Preset field names to Godot literal strings.
    """
    for key, value in settings.items():
        if key not in _PRESET_FIELDS:
            fail("Unsupported preset_settings key %s; use settings/export_options for their namespaces, godot_project.custom_features for custom features" % key)
        if key == "script_export_mode" and value.strip() not in ["0", "1", "2"]:
            fail("preset_settings.script_export_mode must be integer 0, 1 or 2")

def validate_custom_feature(setting, tag, engine_tags):
    """
    Validate a custom feature a project's build setting gives.

    Args:
        setting: Label of the build setting, which messages name.
        tag: The custom feature.
        engine_tags: The feature tags Godot or the configuration sets, which a custom
            feature cannot claim: ENGINE_FEATURE_TAGS.
    """
    if any([c not in _IDENTIFIER_START + _DIGITS + "-" for c in tag.elems()]):
        fail("%s: custom feature %r may hold only letters, digits, _ and -" % (setting, tag))
    if tag in engine_tags:
        fail("%s: custom feature %s is a feature tag Godot or the configuration sets" % (setting, tag))

def _is_identifier(name):
    if not name or name[0] not in _IDENTIFIER_START:
        return False
    return all([c in _IDENTIFIER_START + _DIGITS for c in name.elems()])

def validate_autoloads(autoloads):
    """
    Validate autoload names and resource path syntax.

    Args:
        autoloads: Dictionary of names to res:// paths, optionally prefixed '*'.
    """
    for name, path in autoloads.items():
        if not _is_identifier(name):
            fail("Invalid Godot autoload name: %r" % name)
        value = path[1:] if path.startswith("*") else path
        if not value.startswith("res://") or not value[len("res://"):]:
            fail((
                "Autoload %s must be a res:// path with optional '*' " +
                "singleton prefix"
            ) % name)
