# Fixtures of godot/platforms/private/tests/library_composition

Each section names a fixture and what it reproduces for the tests of this package.

## android_apps_with_transitive_platform_libraries

Android applications of one Godot project whose add-on brings an Android library with an
exported manifest and a plugin AAR that keeps its permissions, and whose pack ships a C
ABI extension. Further applications reach a library with a permission and a resource value
through the application's `platform_deps`, the project or an extension's `platform_deps`;
one overrides that value with its own `platform_resources`, and one fills a library's
manifest placeholder through `android_manifest_values`. The `permissions_*` applications
combine a library that removes a permission with `tools:node="remove"` and one that
declares it, in both orders, with the remover one or two levels below the libraries the
application names, and with the permission declared by the application's manifest or its
pack's export options. A file group stands in for a selected input that Android cannot
use; `android_distribution` exports for both Android CPUs.

## ios_apps_with_transitive_platform_libraries

iOS applications of one Godot project whose add-on brings Swift and Objective-C libraries,
a bundle resource and an Info.plist fragment, and whose C++ extension depends on a support
library and on an SDK with a resource bundle. Further applications reach a platform
resource through the application's `platform_deps`, the project or an extension's
`platform_deps`, or bundle an application-only resource; one application's extension
library is a prebuilt static XCFramework.
