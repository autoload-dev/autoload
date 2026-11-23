"""
Engine components.

godot_editor_component and godot_runtime_component declare the editor or the runtime of one
slot and its toolchain registration. See [engines](../../engine.md).
"""

load(
    "//godot/engine/private:components.bzl",
    _godot_editor_component = "godot_editor_component",
    _godot_runtime_component = "godot_runtime_component",
)

godot_editor_component = _godot_editor_component
godot_runtime_component = _godot_runtime_component
