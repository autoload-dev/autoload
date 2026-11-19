"""
The application backends of godot_app, for platform tests that declare one directly.

A backend packages a pack for one operating system; godot_app selects it by the export
platform. Platform tests use them to inspect one backend's shell files or packaging.
"""

load("//godot/platforms/private:android.bzl", _godot_android_application = "godot_android_application")
load(
    "//godot/platforms/private:desktop.bzl",
    _godot_linux_application = "godot_linux_application",
    _godot_macos_application = "godot_macos_application",
)
load("//godot/platforms/private:ios.bzl", _godot_ios_application = "godot_ios_application")
load("//godot/platforms/private:macos_signing.bzl", _godot_macos_sign = "godot_macos_sign")

visibility(["//godot/platforms/private/tests/..."])

godot_android_application = _godot_android_application
godot_ios_application = _godot_ios_application
godot_linux_application = _godot_linux_application
godot_macos_application = _godot_macos_application
godot_macos_sign = _godot_macos_sign
