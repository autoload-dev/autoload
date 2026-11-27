"""Extensions, and the extension libraries rules_cc builds for them."""

load("//godot/extension/private:cc_extension.bzl", _godot_cc_extension = "godot_cc_extension")
load("//godot/extension/private:extension.bzl", _godot_extension = "godot_extension")

godot_extension = _godot_extension
godot_cc_extension = _godot_cc_extension
