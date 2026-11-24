# rules_godot examples

This standalone Bazel module shows how to consume rules_godot through its public rules.
[Project layout](../rules_godot/docs/public/project-layout.md) explains how its add-ons, demos and
tests are organized.

Add-ons, each with a `demo/` project and a `tests/` project:

- [AppAuth](addons/app_auth/README.md) logs a player in with OpenID Connect through the
  AppAuth SDKs on Android, iOS and macOS.
- [Dart scripts](addons/dart/README.md) adds Dart as a script language, compiled ahead of
  time into the project's extension with an embedded Dart VM built from source.
- [Platform Paths](addons/platform_paths/README.md) exposes operating-system storage
  locations through one typed API on macOS, Linux, iOS and Android.
- [SQLite](addons/sqlite/README.md) builds the SQLite C library and exposes parameterized
  in-memory queries to GDScript.

Projects:

- [Lichtpost](lichtpost/README.md) is a one-button courier game with tests, an
  editor view and application packaging.
- [Petri](petri/README.md) grows reaction-diffusion cultures with a source-built
  engine and its own C++ module.

## Getting started

1. Install Bazelisk and a host C/C++ toolchain. On macOS, select Xcode's command
   line tools.
2. From the repository root, run:

   ```sh
   bazel run //examples/addons/sqlite/demo:run
   ```

   The window shows **SQLite says: Hello from SQLite**.

Follow the add-on README for its API and tests and the
[platform guide](../rules_godot/docs/public/platforms.md) for Android/iOS SDK setup, source-built
engines and release artifacts.

## Working on an example

Keep an example's tests in its own project or test package. Declare its inputs
and dependencies in this module; the parent ruleset's development dependencies
are not inherited. See [the example guidance](AGENTS.md).
