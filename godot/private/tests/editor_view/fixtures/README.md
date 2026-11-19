# Fixtures of godot/private/tests/editor_view

Each section names a fixture project and what it reproduces for the tests of this package.

## project_edited_in_the_view

A project whose enabled editor plugin edits it in the editor view as a user would: it
rewrites a script, adds a resource and a file of the view only, and saves a description
and a contributed setting into `project.godot`. The project also holds a plugin enabled
only in the authored `project.godot`, a C ABI extension, a contributed setting and
checkout files without declared sidecars. `project_without_extension` is the same project
with the extension disabled for the editor.

## project_with_declared_sidecars

A script whose UID sidecar is declared beside it, on the ruleset's default project file:
a checkout that godot_metadata_sync finds complete.
