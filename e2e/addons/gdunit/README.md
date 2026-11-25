# autoload_gdunit's end-to-end tests

The tests in this package run `gdunit_test` as an application does, in two projects; each
section names one and what it reproduces for the tests of this package.

## gdunit_suites

GdUnit suites in one project: three passing suites, one of them generated, whose path order
decides the round-robin split across shards; a failing suite; a suite without tests; a suite
whose only test is skipped; and a suite that leaves an orphan node. The suites that must fail
have their own manual tests.

## strict_warnings

A project whose `project.godot` treats every GDScript warning as an error, below
`res://addons/` too except in GdUnit itself, so that the GdUnit adapter runs under these
settings.
