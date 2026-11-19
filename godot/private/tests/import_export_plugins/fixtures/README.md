# Fixtures of godot/private/tests/import_export_plugins

Each section names a fixture project and what it reproduces for the tests of this package.

## project_with_import_and_export_plugins

A project that names an add-on whose importer converts `.greeting` files and packs an
add-on whose editor part registers an export plugin, which no export runs. The importer's
add-on has an icon in its editor part, and its editor plugin crashes Godot while it shuts
down in every process that stages it. The authored `project.godot` names a theme only the
whole project contains, a release channel with a feature override, and enables a plugin
whose export hook fails any export it runs in. `release_project` gives its builds the
channel `integration_test` as a custom feature from the build setting `release_channel`.
The main scene checks the theme, the imported texture and the converted greeting, and
compares the release values it sees with its first argument after Godot's `--` separator.
