# Fixtures of godot/private/tests/pack_membership

Each section names a fixture project and what it reproduces for the tests of this package.

## project_with_pack_variants

One game exported as several packs: a brand file placed per pack at one resource path, a
pack with compressed scripts, a data-only pack of a glob of levels and a generated file, a
reachable base pack and a DLC pack that requires it, each with a global class of its own, and two packs with a C ABI extension,
one reachable and one that requires the data pack. The main scene reads its raw data through
literal paths and checks the brand passed after Godot's `--` separator.
