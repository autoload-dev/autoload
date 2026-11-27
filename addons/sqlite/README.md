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
   From the repository root, run:

   ```sh
   bazel run //examples/addons/sqlite:run
   ```

2. The window displays **SQLite says: Hello from SQLite** after creating a table,
   binding a string and reading it through the extension library.
3. Run the add-on's own tests without a graphical display:

   ```sh
   bazel test //examples/addons/sqlite/tests:exported
   ```

   Building it validates the GDScript; the test loads the extension from an exported
   production pack and runs the demo's query.

## Reuse the add-on

`//sqlite` is an add-on of only its extension. List it in the `deps` of the
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

Run from the repository root:

```sh
bazel run //examples/addons/sqlite:edit
bazel run //examples/addons/sqlite:update
bazel build //examples/addons/sqlite:pack
```

The [project layout guide](../../rules_godot/docs/public/project-layout.md) explains the separate
add-on, demo and test packages, explicit dependencies and sidecars. The
[platform guide](../../rules_godot/docs/public/platforms.md) provides the SDK setup, application
targets, [CPU selection](../../rules_godot/docs/public/platforms.md#export-platforms),
source-built and prerelease engines and release-symbol commands.

The extension's C++ code is in [`database.cc`](sqlite/database.cc). The
[module](MODULE.bazel) pins the official [SQLite amalgamation](https://www.sqlite.org/amalgamation.html)
by URL and digest; its [BUILD file](third_party/sqlite.BUILD.bazel) compiles the
C library independently from the C++ binding. GdUnit and its suites belong to
the Godot test project's `database/` package and are absent from production packs.
