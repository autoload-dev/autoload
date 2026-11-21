# Fixtures of //tests

Each section names a fixture and what it reproduces for the tests of this package.

## gdunit_suites

GdUnit suites in one project: three passing suites, one of them generated, whose path order
decides the round-robin split across shards; a failing suite; a suite without tests; a suite
whose only test is skipped; a suite that leaves an orphan node; and a suite whose assertion on
a native extension's result fails. The suites that must fail have their own manual tests.

## native_counter

A godot-cpp extension class, `NativeCounter`, behind a GDScript wrapper at
`addons/native_counter/counter.gd`, so that a suite reaches native code through a script.

## strict_warnings

A project whose `project.godot` treats every GDScript warning as an error, below
`res://addons/` too except in GdUnit itself, so that the GdUnit adapter runs under these
settings.
