# Fixtures of godot/private/tests/resource_graph

Each section names a fixture and what it reproduces for the tests of this package.

## project_with_generated_declarations

A project whose scene, script and resource are declared by the macro `godot_build_files`
generates, with the runtime references of the script and the scene declared in BUILD, and
the resource graph over it that requires declared edges.
