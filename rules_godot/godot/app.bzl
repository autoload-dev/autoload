"""
Build applications: `godot_app` packages a start pack and the runtime of the selected export
platform; `godot_configured_app` builds one under an export platform and build settings of
its own, with `ANDROID_RELEASE` and `APPLE_RELEASE` as release settings.

Select the export platform with --platforms; use target_compatible_with for consumer
limits.
Export content and Godot configuration belong to the declared pack/project.
"""

load("//godot/private:app.bzl", _godot_app = "godot_app")
load(
    "//godot/private:configured_app.bzl",
    _ANDROID_RELEASE = "ANDROID_RELEASE",
    _APPLE_RELEASE = "APPLE_RELEASE",
    _godot_configured_app = "godot_configured_app",
)

godot_app = _godot_app

godot_configured_app = _godot_configured_app

#: The native settings of an Android release whose debug symbols ship apart: optimized,
#: with DWARF, stripped in the application. Volatile API, like godot_configured_app.
ANDROID_RELEASE = _ANDROID_RELEASE

#: The native settings of an Apple release whose debug symbols ship apart: optimized, with
#: dSYMs, stripped in the application. Volatile API, like godot_configured_app.
APPLE_RELEASE = _APPLE_RELEASE
