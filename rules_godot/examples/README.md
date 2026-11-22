# rules_godot examples

This standalone Bazel module shows how to consume rules_godot through its public
rules. The [SQLite add-on](addons/sqlite/README.md) builds the SQLite C library
and exposes parameterized in-memory queries to GDScript. Its `demo/` project includes
an editor view and application targets for Linux, macOS, Android and iOS;
`tests/` owns the add-on's Godot test project, with `unit/` for deterministic API
suites and `integration/` for operating-system behavior suites where needed. Both add-ons
keep demo application content under `main/` and Godot suites/fixtures in the test project.

[Platform Paths](addons/platform_paths/README.md) demonstrates operating-system storage APIs
behind a common typed extension API on macOS, Linux, iOS and Android. Run
`bazel run //addons/platform_paths/demo:run` to inspect the five directory categories.

[Dart scripts](addons/dart/README.md) adds Dart as a script language: `.dart` files attach to
nodes as GDScript files do, compiled ahead of time into the project's extension with an
embedded Dart VM built from source. Run `bazel run //addons/dart/demo:run` to see three Dart
scripts at work.

[Lichtpost](projects/lichtpost/README.md) is a one-button courier game; from this directory,
`bazel run //projects/lichtpost:run` opens it for play.

[Petri](projects/petri/README.md) grows reaction-diffusion cultures in a petri dish with a
source-built engine and its own C++ module; `bazel run //projects/petri:run --config=petri`
opens it.

## Getting started

1. Install Bazelisk and a host C/C++ toolchain. On macOS, select Xcode's command
   line tools.
2. From the repository root, run:

   ```sh
   cd examples
   bazel run //addons/sqlite/demo:run
   ```

   The window shows **SQLite says: Hello from SQLite**.

Follow the add-on README for its API and tests, the
[project layout guide](../docs/public/project-layout.md) for its complete development
cycle, and the [platform guide](../docs/public/platforms.md) for Android/iOS SDK setup,
source-built engines and release artifacts.

## Working on an example

Keep an example's tests in its own project or test package. Declare its inputs
and dependencies in this module; the parent ruleset's development dependencies
are not inherited. See [the example guidance](AGENTS.md).
