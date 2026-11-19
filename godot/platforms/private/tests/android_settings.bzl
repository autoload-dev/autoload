"""Configuration and compatibility shared by the Android analysis tests of this package."""

load("//godot/private/tests:toolchains.bzl", "own_toolchains")

# The application for Android and iOS whose project selects each operating system's platform
# library.
MOBILE_FIXTURE = "//godot/platforms/private/tests/fixtures/mobile_app_with_platform_libraries:"

# The Android SDK and NDK toolchains, registered as the analyzed module's own.
ANDROID_TOOLCHAINS = own_toolchains(["@androidsdk//:all", "@android_toolchains//:all"])

# An arm64 Android application with those toolchains.
ANDROID = {
    "//command_line_option:platforms": str(Label("//godot/platforms:android_arm64")),
} | ANDROID_TOOLCHAINS

# Android applications and imports need an installed Android SDK; without one the tests are
# skipped.
ANDROID_SDK = {"size": "small", "target_compatible_with": [Label(":requires_android_sdk")]}
