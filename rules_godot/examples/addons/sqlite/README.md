# SQLite add-on

Link SQLite's C amalgamation into a Godot GDExtension and use parameterized SQL
from GDScript. The add-on builds its own SQLite library; it does not use a system
installation. Its small `SQLiteDatabase` class owns one in-memory connection:

```gdscript
var database = SQLiteDatabase.new()
database.open()
database.execute("CREATE TABLE messages (text TEXT)")
database.execute("INSERT INTO messages VALUES (?)", ["Hello from SQLite"])
var rows: Array = database.query("SELECT text FROM messages")
database.close()
```

## Getting started

1. Install Bazelisk and a native C/C++ toolchain: Xcode Command Line Tools on
   macOS or GCC/Clang on Linux.
   From the repository root, enter the examples module:

   ```sh
   cd rules_godot/examples
   bazel run //addons/sqlite/demo:run
   ```

2. The window displays **SQLite says: Hello from SQLite** after creating a table,
   binding a string and reading it through the extension library.
3. Run the add-on's own tests without a graphical display:

   ```sh
   bazel test //addons/sqlite/tests/unit //addons/sqlite/demo/tests:exported
   ```

   Building them validates the GDScript; the tests check parameterized round trips,
   values and errors, and load the extension from an exported production pack.

## Reuse the add-on

`//addons/sqlite` is an add-on of only its extension. List it in the `deps` of the
`godot_resources` whose scripts use it, or in a `godot_project`'s `deps` when no content
of the project uses it. Its descriptor is mounted at
`res://addons/sqlite/sqlite.gdextension`. The public `godot_cc_extension` rule
builds a shared library on desktop and Android and a static archive on iOS.

`open()` creates a new in-memory database and returns a boolean. It rejects an
already open connection. `execute(sql, parameters)` returns a boolean;
`query(sql, parameters)` returns an array of dictionaries, keyed by column name.
Use `execute` for statements without result columns and `query` for statements
that return rows. A mismatched call fails. Both accept one SQL statement with
no trailing SQL comments and an optional array of bound values: null,
boolean, integer, float, string or `PackedByteArray`. Parameters bind values,
not SQL identifiers. A failed call sets `get_last_error()`; a failed query returns
an empty array. `close()` releases the connection, as does object destruction.
The class deliberately exposes no filesystem database or extension-loading API.

## Develop and package

Run from `rules_godot/examples/`:

```sh
bazel run //addons/sqlite/demo:edit
bazel run //addons/sqlite/demo:update
bazel run //addons/sqlite/tests:update
bazel build //addons/sqlite/demo:pack
```

The [project layout guide](../../../docs/public/project-layout.md) explains the separate
add-on, demo and test packages, explicit dependencies and sidecars. The
[platform guide](../../../docs/public/platforms.md) provides the SDK setup, application
targets, [CPU selection](../../../docs/public/platforms.md#export-platforms),
source-built and prerelease engines and release-symbol commands.

The extension's C++ code is in [`database.cc`](database.cc). The
[module](../../MODULE.bazel) pins the official [SQLite amalgamation](https://www.sqlite.org/amalgamation.html)
by URL and digest; its [BUILD file](../../deps/sqlite.BUILD.bazel) compiles the
C library independently from the C++ binding. GdUnit and its suites belong to
the Godot test project's `unit/` package and are absent from production packs.
