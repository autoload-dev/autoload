# Fixtures of godot/private/tests

Each section names a fixture project and what it reproduces for the tests of this package.

## import_context

Resources composed into projects: add-ons with settings and autoloads that reach a project
through deps and import inputs, files placed at explicit resource paths (generated, from another
repository, from a subpackage with its own prefix), sources with and without their
sidecars, add-on prefixes, a C ABI extension, a pack of every member, and a target named
like the subpackage `textures/`, whose import units must not nest. `foreign/` holds the
files that tests place at resource paths other than their own.

## minimal_project

A one-scene project and its pack: the smallest graph on which the `godot_actions` aspect
reaches the Godot actions of a pack.

## project_with_imported_assets

Two imported SVG assets, a script and a main scene, exported with an explicit script export
mode: which edits reach the import, the metadata index and the pack.

## project_with_importer

A project that names an add-on whose importer converts `.md` files and reads a setting,
with a unit with an own `.md` file, a texture unit and a unit with an `.md` file only among
its import inputs; a project that does not name the add-on; and a project that names the
same importer in an add-on with an own `.md` file: which imports, initializations and
exports stage the importer, resources that use it under a project that does not name it,
and an add-on whose own file needs its own importer.

## project_with_native_extension

A script, a raw text resource and a C ABI extension that the editor does not load, plus a
test that reads the pack and a runtime-only data file: edits that reach the pack, the
metadata index or no Godot action at all.

## project_with_pack_membership

A brand file chosen per pack, a shared script, a glob of level files, a generated resource,
a dependent pack with its own entry point and a test-only script that no pack reaches: pack
membership and pack selection inputs.

## project_with_addons

Content that uses an add-on with a runtime part, an autoload, a setting and an extension,
which needs a second add-on, and a project that names an editor-only add-on with an
imported icon: what the operations of the project contain, what each import
stages, an add-on that needs an extension outside its directory, and the add-on
declarations analysis rejects.

## project_with_shared_unit

Imported SVG units that a pack, a test and a check of one project share and a check of a
second project reaches too, with an import input, an autoload script, the main scene, a C
ABI extension and the editor part of an add-on the project names beside them, which
registers an export plugin: which operations share an import, and which edits rerun one.

## reproducible_project

Two imported SVG assets and a script whose import and export the reproducibility test runs
twice.
