# Fixtures of godot/engine/private/tests

Each section names a fixture and what it reproduces for the engine configuration tests.

## The fixtures package itself

One registration set: editor and runtime components of every desktop slot, registered
through `:all`, and a CcInfo stand-in for iOS payloads, which are never linked.

## editor_only

A registration set with an editor alone; the runtime still comes from the registered hub.

## forward

A component that reuses a component of another registration set, whose payload and
provenance are forwarded.

## invalid

Mobile runtimes without their payload provider (JavaInfo or CcInfo), and payloads whose own
slot facts contradict the declared slot, also through forwarding.

## release_override

A registration set of the desktop release runtime slots alone, registered ahead of the
prebuilt hub, which keeps every other slot.

## remote_editors

Editors of stand-in remote execution platforms: tests may run there, `bazel run` launches
never do.

## select

A runtime component whose payload selects on the compilation mode.

## select_recipe

A choice between two prepared components of one slot whose unselected branch is a recipe
that fails to configure, so selecting the fixture component never fetches it.

## simulator_override

One replaced iOS simulator slot, registered ahead of the full registration set.

## source_build

The `bazel_probe` engine module and the engine patch of the ruleset's own source-built
engines.

## source_built_ios

A source-built engine library with Swift code and a bundled resource, which the replayed
Apple aspects must reach through the library's dependencies.

## source_built_runtime

A macOS application whose runtime is built from engine sources with the `bazel_probe`
module, as a generated source-build repository declares it, while the prebuilt editor
imports and exports. Its native graph is analyzed, never built.
