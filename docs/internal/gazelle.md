# Gazelle for Godot

The repository's Gazelle language `godot` ([tools/gazelle/godot](../../tools/gazelle/godot))
writes the BUILD declarations of Godot projects: a `godot_project` beside each `project.godot`,
a `godot_resources` target per import unit with the dependencies its files reference, and a
`gdunit_test` for each package of GdUnit suites. Everything else in a BUILD file, such as
packs, applications, editor views, extensions and add-ons, stays hand-written. It runs with the
ruleset's `bzl_library` generation (see [generated BUILD declarations](verification-recipes.md#generated-build-declarations)):

```sh
bazel run //tools/gazelle:update      # write the BUILD files
bazel run //tools/gazelle:check       # fail with the difference where one is stale
```

The run `//tools/gazelle:root` covers `examples/` and `e2e/` of the root module. The root
[BUILD file](../../BUILD.bazel) holds its directives.

## What it declares

**Packages.** The language works inside Godot projects only: below a directory that holds a
`project.godot`, without the directories Godot skips (those with a `.gdignore`, hidden ones and
nested projects, which are projects of their own). A project's directory always becomes a
package. Every other directory is a package only when it holds a BUILD file: the language never
creates one there, and the files of a directory without one belong to the nearest package
above. Adding an empty `BUILD.bazel` draws a
[package boundary](../../rules_godot/docs/public/project-layout.md#build-files-and-package-boundaries);
the next run fills it.

**Resources.** A file is a resource when its format is one Godot loads (scenes, scripts,
resources, shaders, images, audio, fonts, models), when it has a sidecar, such as a script of
another language with its `.uid`, or when a file of its package names its `res://` path. Its
sidecars always go with it. The resources of a package form import units:

| Import unit | Files | Name |
|---|---|---|
| An asset | An importable file with its `.import`, a glTF with its buffers and images | The file's stem, such as `gardens_far` for `gardens-far.png`; with the format where another unit has the name |
| The suites | The scripts that extend `GdUnitTestSuite` | `suites` |
| A directory | The other resources of the package's directory or of a subdirectory without a package | The package's name; `fixtures` in a package of suites; `resources` in a project's own package; a subdirectory's path below the package, such as `courier` |

Each `godot_resources` target has `prefix` set to its package's directory relative to the
project, so that its files appear at their places in the project.

**Projects.** `godot_project` is named after its directory and sets `project_file`. A new BUILD
file of a project also makes the project visible to the packages below it.

**Tests.** A package with suites gets a `gdunit_test` named after the package, or `tests` in a
project's own package, which names the project and runs the units that hold suites. It gets none
when a `gdunit_test` of the package already runs some of its suites but not all, or where
`# gazelle:godot_gdunit_test disabled` applies.

## Attributes it owns

| Kind | Attributes the language sets | Left to a person |
|---|---|---|
| `godot_resources` | `srcs`, `prefix`, `strip_prefix`, `deps`, `runtime_deps` | Every other attribute, such as `visibility`, `testonly`, `tags`, `resource_paths`, `import_inputs` and `runtime_references` |
| `godot_project` | `project_file`; `visibility` in a new BUILD file | Every other attribute, such as `main_scene`, `settings` and `deps` |
| `gdunit_test` | `project`, `suites` | Every other attribute, such as `size`, `tags` and `shard_count` |

Gazelle replaces an owned attribute and keeps the others. It deletes a `godot_resources`
target whose files are all gone.

## Dependencies

`deps` lists the targets that provide what a unit's files reference when Godot loads them:

- a `.tscn` or `.tres` file's external resources, by `path` and by `uid`;
- a script's `extends "res://…"`, its literal `load()` and `preload()` paths and UIDs, its
  `@icon`, and every name that may be a global class, from `extends` to type hints and calls;
- a shader's `#include` paths.

`runtime_deps` lists the targets that provide the files a script reads with `FileAccess` from
a literal `res://` path. Paths a script builds at runtime, such as a `load()` of a variable,
stay undetected and are declared by hand.

The ruleset's resource graph scanner reads these references, the same scanner whose graph
checks the declarations at build time
([detected references](../../rules_godot/docs/public/resources.md#detected-references)).

A target provides the `res://` paths and UIDs of its files and the global classes their
`class_name` declares. An extension provides its `resource_path` and the classes its C++
sources in the package register (`register_class<…>`, `GDREGISTER_CLASS(…)`); an add-on
provides every path below its `directory`. Paths and class names hold within one project:
a reference resolves to a target of the referencing project, or to one outside every project,
such as an add-on, never to another project's. A built-in class resolves to nothing. A
reference that several targets provide resolves to nothing too, with a message that asks for
a resolve directive.

## A person's choices

- **Grouping and names.** A `godot_resources` target keeps the files its `srcs` list,
  whatever its name; new files join the unit their kind gives them. Splitting a unit or
  renaming a target is an edit the next run preserves. A file that a target of another kind
  lists, such as a `godot_addon`, belongs to no unit. Labels and generated files in `srcs` stay.
- **`# keep`.** On a target, Gazelle leaves the whole target alone; on an attribute, that
  attribute; on one entry of `deps`, that entry, such as an umbrella dependency the files do not
  reference. The language resolves nothing for a kept `deps` or `runtime_deps`, so a
  reference that several targets provide reports nothing there.
- **Renamed projects and tests.** A `godot_project` matches by `project_file`, a `gdunit_test`
  by `suites`, so either may carry another name.
- **Opaque `srcs`.** A package with a `godot_resources` target whose `srcs` is no list of
  strings, such as a `glob` or a concatenation, keeps its resource targets as they are.

## Directives

| Directive | Effect |
|---|---|
| `# gazelle:godot_extension enabled\|disabled` | Whether the language declares anything in this directory and below |
| `# gazelle:godot_gdunit_test enabled\|disabled` | Whether it declares GdUnit tests there |
| `# gazelle:resolve godot class <Name> <label>` | The target that provides a global class, such as an add-on module's extension class |
| `# gazelle:resolve godot res res://<path> <label>` | The target that provides a resource path |
| `# gazelle:resolve godot uid uid://<id> <label>` | The target that provides a UID |
| `# gazelle:resolve_regexp godot res <regexp> <label>` | The target that provides every matching resource path, such as the `.dart` scripts of a Dart extension |

The resolve directives are Gazelle's own; `class`, `res` and `uid` are the kinds of reference.
A directive takes precedence over the index. Gazelle's `map_kind` applies to the three kinds.

## Design

- **Placement.** The language is a package of the root module beside the Gazelle runs that
  use it, and depends only on Gazelle's packages and on the ruleset's scanner through its public label. Published, it becomes a module of its own
  beside the ruleset, as `rules_python_gazelle_plugin` and `bazel_skylib_gazelle_plugin` sit
  beside theirs: a `MODULE.bazel` with `gazelle`, `rules_go`, `rules_python` and
  `autoload_rules_godot`, whose `//tools:resource_graph_lib` stays public, a registry test module in
  `bcr/`, a release workflow and its tests run from the root module. A user then adds it to
  their `gazelle_binary`'s `languages`. The loads it writes follow the apparent names of
  `autoload_rules_godot` and `autoload_gdunit` in the user's module.
- **Reference scanning.** The knowledge of Godot's formats lives in one place, the ruleset's
  resource graph scanner in Python, which the ruleset's build tools import. The language's Go
  code knows no format: [scanner.py](../../tools/gazelle/godot/scanner.py) calls the
  scanner's `file_references` and adds only the classes an extension's C++ sources register.
  As in the Gazelle plugin of rules_python, the language starts the scanner once per run,
  on its first scan, sends it one JSON line per package on stdin and reads one line back;
  it stops it after resolving the dependencies, and a scanner that cannot start or answer
  ends the run. Unlike rules_python, which embeds its helper and runs it with the host's
  `python3`, the scanner is a `py_binary` that the language finds in its runfiles, with the
  hermetic interpreter the ruleset needs; `GAZELLE_GODOT_SCANNER` names another program.
  A run over `examples/` and `e2e/` (341 files) takes about half a second, of which the
  scanner's start is about 0.3 s.
- **Gazelle version.** It is written against Gazelle 0.51.3, the version of the root module.
  There the packages `rule` and `label` are already aliases of the `v2` module, while
  `language`, `config` and `resolve` have no `v2` form yet. Gazelle 2.0, in beta, moves load
  information onto `KindInfo`, passes a directory cache to `Imports` and `Resolve` and makes
  `GenerateResult.Imports` optional; moving changes the language's entry points, not its
  scanning, grouping or resolution.

## Tests

The ruleset's `//tools/tests:file_references_test` tests `file_references`,
[scanner_test.py](../../tools/gazelle/godot/scanner_test.py) the scanner program, and
`//tools/gazelle/godot:generation_test` runs Gazelle over each tree in
[testdata](../../tools/gazelle/godot/testdata) and compares the BUILD files it writes with
the trees' `BUILD.out` files: a new tree of two projects and a tree whose BUILD files a person
edited. `second_run_test` runs Gazelle over the first tree with its `BUILD.out` files as
input, which a second run must leave unchanged. After an intended change of the output,
`UPDATE_SNAPSHOTS=true bazel run
//tools/gazelle/godot:generation_test` rewrites the expected files.
