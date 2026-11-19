"""
Test what a built Android App Bundle or iOS application contains, without a device.

`android_bundle_test` inspects the APK bundletool generates from a godot_app's App Bundle;
`ios_app_test` inspects a godot_app's iOS application. Both run as ordinary Bazel tests on
the execution platform, so a mobile build can be checked where it is built, such as for
the native libraries of an add-on or the resources of the pack. Neither installs nor runs
the application. See [platform prerequisites](../../platforms.md) for the Android SDK and
Xcode setup the applications need.
"""

load("//godot/testing/private:android_bundle_test.bzl", _android_bundle_test = "android_bundle_test")
load("//godot/testing/private:ios_app_test.bzl", _ios_app_test = "ios_app_test")

visibility("public")

android_bundle_test = _android_bundle_test
ios_app_test = _ios_app_test
