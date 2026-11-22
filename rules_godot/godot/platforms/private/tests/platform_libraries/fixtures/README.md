# Fixtures of godot/platforms/private/tests/platform_libraries

Each section names a fixture and what it reproduces for the tests of this package. The
Android and Apple libraries are stand-ins from `library_fixtures.bzl` that need no C/C++ or
Java toolchain.

## addons_with_platform_libraries

A utility add-on with an Info.plist fragment and an Apple library, and an add-on that uses
it, brings Android and Apple libraries and ships two extensions: one with an Apple platform
library, one with an iOS library per CPU. A project of them and its pack: which platform
libraries and fragments the project collects, and which an iOS application links.

## extensions_without_matching_libraries

An extension with a library for Linux only, and Android and iOS extensions in a project that
disables them for runtime: applications that deliver none of their libraries.

## extension_library_declarations

An extension with a shared library where iOS links static ones, one whose iOS library is a
dynamic framework, an Android library with a shared library beside it, and two extensions whose Android libraries have one file name:
which an application accepts and which fail its analysis.
