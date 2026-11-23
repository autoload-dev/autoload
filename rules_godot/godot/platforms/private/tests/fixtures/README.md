# Fixtures of godot/platforms/private/tests

Each section names a fixture and what it reproduces for the tests of this package.

## apps_with_editor_plugin_and_autoload

Two macOS applications that differ only in `application_id`, over one pack with an add-on
whose editor part registers an export plugin and whose project autoloads a script: which
edits reach the pack and the shell assets and which leave the project's actions unchanged.

## macos_app_with_extension

A macOS application with declared entitlements whose pack ships a native extension: the
actions that the signing mode and the entitlements reach.

## mobile_app_with_platform_libraries

One application for Android and iOS whose project selects each operating system's platform
library, with an application platform library, a platform resource and, on Android, a
manifest placeholder value: which platform inputs reach the bundle and which reach neither
the bundle nor the content actions.

## maven_coordinates

A Java source that compiles against Maven-tagged libraries: the coordinates the Maven minimum
check's aspect collects along `deps`, `exports` and `runtime_deps`.
