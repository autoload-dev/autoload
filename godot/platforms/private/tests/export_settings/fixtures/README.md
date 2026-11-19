# Fixtures of godot/platforms/private/tests/export_settings

Each section names a fixture and what it reproduces for the tests of this package.

## packs_with_and_without_version_options

Android and iOS packs that set no version export options beside packs that set them, and a
pack beside one that sets its own `application/config/version`: which version the shell
files and the pack's configuration take under the release build settings
`//godot:app_version` and `//godot:build_number`. The packs without options export a
portrait game on the Compatibility renderer, whose Android bootstrap, iOS shell files and
export facts follow its project settings and Godot's defaults.

## packs_with_export_options

Android and iOS packs that set the exporters' export options (names, permissions, screen,
privacy, capabilities and versions) over a project with its own name and version, and the
project's macOS pack, which sets none: the shell files follow the options, and the macOS
export facts list the exporter's options.
