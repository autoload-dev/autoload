# Fixtures of godot/platforms/private/tests/app_platform_selection

Each section names a fixture and what it reproduces for the tests of this package.

## project_with_desktop_apps

A project with a start pack and a desktop application of it: what a direct pack and an
application run.

## app_selecting_platform_libraries

One `godot_app` declaration for desktop, Android and iOS whose project ships a C ABI
extension and selects each mobile operating system's add-on:
a Java library and an AAR on Android, a Swift and an Objective-C library with an
Info.plist fragment and a platform resource on iOS: which backend, libraries and resources
each platform's application contains, and what an Android application and its debug
symbols companion deliver.

## export_platforms_with_both_cpus

Export platforms with both CPUs of Android (`android_distribution`, and `common_android`,
which inherits a base platform's constraint) and of the iOS Simulator
(`simulator_distribution`), each with a constraint of its own: applications for both
CPUs of one operating system.
