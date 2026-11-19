# Fixtures of godot/private/tests/import_context_runs

Each section names a fixture project and what it reproduces for the tests of this package.

## composed_configuration

Resources that set the application name and a `State` autoload, composed into three projects:
one that overrides the name directly, one that reaches the resources through a resource with
an import input whose own name and `ImportInputState` autoload must stay private, and one
that overrides the setting and the autoload a dependency declares. Its check script reads the
expected name after Godot's `--` separator.
