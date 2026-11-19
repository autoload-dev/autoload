"""
Engine components and the Android runtime payload.

godot_editor_component and godot_runtime_component declare the editor or the runtime of one
slot and its toolchain registration; godot_android_runtime combines the Android shell
library with the engine library into an Android runtime payload. See
[engines](../../engine.md).
"""

load(
    "//godot/engine/private:components.bzl",
    _godot_editor_component = "godot_editor_component",
    _godot_runtime_component = "godot_runtime_component",
)
load("//godot/platforms/private:android.bzl", _godot_android_runtime = "godot_android_runtime")

godot_editor_component = _godot_editor_component
godot_runtime_component = _godot_runtime_component
godot_android_runtime = _godot_android_runtime
