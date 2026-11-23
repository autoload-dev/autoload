// swift-tools-version: 5.9
// The Swift packages of the examples module; rules_swift_package_manager resolves them from
// Package.resolved. Refresh the pin with `swift package resolve` from this directory.
import PackageDescription

let package = Package(
    name: "rules_godot_examples",
    dependencies: [
        .package(url: "https://github.com/openid/AppAuth-iOS.git", exact: "3.0.0"),
    ]
)
