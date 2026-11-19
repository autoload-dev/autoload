# Fixtures of godot/private/tests/gdunit

Each section names a fixture and what it reproduces for the tests of this package.

## gdunit_suites

GdUnit suites in one project: three passing suites, one of them generated, whose path order
decides the round-robin split across shards; a failing suite; a suite without tests; a suite
whose only test is skipped; and a suite whose assertion on a native extension's result
fails. The suites that must fail have their own manual launchers.

## native_counter

A godot-cpp extension class, `NativeCounter`, behind a GDScript wrapper at
`addons/native_counter/counter.gd`, so that a suite reaches native code through a script.
