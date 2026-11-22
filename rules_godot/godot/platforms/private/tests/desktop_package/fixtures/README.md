# Fixtures of godot/platforms/private/tests/desktop_package

Each section names a fixture and what it reproduces for the tests of this package.

## desktop_runtimes_without_engine

Prebuilt desktop runtimes over a shell stub that prints the pack beside it, for Linux and
macOS, a debug variant, a newer version and support files only, plus packs without Godot facts
and a Linux application over them: the runtime contract of desktop packaging without an
engine, and a Linux bundle that runs.

## macos_app_from_project

A macOS application with the stub macOS runtime over Godot's export of a project that sets a
name and a version, and its signed copy: the shell files Godot's export decides and the
bundle signing writes.

## macos_app_with_liquid_glass_icon

A macOS application with the stub macOS runtime over a pack whose
`application/liquid_glass_icon` names a minimal Icon Composer `game.icon` of the project, one
layer over one PNG: the asset catalog Xcode's `actool` compiles from it and the icon name the
Info.plist carries.

## apps_with_native_symbols

A Linux application whose pack ships an extension library: which native code Bazel's
`--strip` strips and what the debug symbols hold.

## macos_apps_with_dsyms

Two macOS applications whose extension rules_cc links: one with a runtime rules_cc links too,
one with the prebuilt stub runtime and an extension built with `--apple_generate_dsym`: which
`.dSYM`s are the linker's and which dsymutil extracts.

## host_test_and_macos_app

A host test and a macOS application with the stub macOS runtime over the same two units of
one project: which Godot actions of the units the two share in one build.
