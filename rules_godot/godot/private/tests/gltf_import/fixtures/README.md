# Fixtures of godot/private/tests/gltf_import

Each section names a fixture and what it reproduces for the tests of this package.

## gltf_with_external_buffer

A glTF scene whose mesh lives in an external `.bin` buffer that the scene's resources take
as an import input, and a pack whose main scene instantiates the imported scene.
