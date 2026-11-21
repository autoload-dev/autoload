# Repository Development

This guide covers BUILD and resource-graph maintenance. For repository checks and timing,
read the [verification policy](verification.md); for a fixture or environment setup, use the
relevant [verification recipe](verification-recipes.md).
For application execution, content validation, GdUnit, editor views and sidecars, see
[development and testing](../public/development.md).

## Analysis and BUILD maintenance

`godot_resource_graph` in `godot/private/analysis.bzl` writes a project's resource graph
for the ruleset's own tests; the scanner scope is described in
[detected references](../public/resources.md#detected-references).
Maintainers can query a test fixture's graph with the repository tool:

```sh
bazel build //godot/private/tests/resource_graph/fixtures/project_with_generated_declarations:graph
bazel run //tools:resource_graph -- query \
  --graph "$PWD/bazel-bin/godot/private/tests/resource_graph/fixtures/project_with_generated_declarations/graph.graph.json" \
  --direction affected res://main/content.tres
```

Queries support reachability and reverse affected-file closure; supplying
`--previous-graph` includes deleted or changed old edges. With a previous graph,
affected UID queries include the previous and current owners of a moved stable UID;
reachability prefers its current owner. These are conservative file graphs, not automatic
Bazel target selection.

For initial BUILD maintenance, the source-manifest generator generates
one marked `.bzl` macro, scans one package without crossing nested Bazel package
boundaries, collects a `.uid` or `.import` sidecar only together with its file, preserves
manual BUILD files, and supports idempotent `--check`:

```sh
bazel run //tools:godot_build_files -- --root "$PWD/path/to/package"
bazel run //tools:godot_build_files -- --root "$PWD/path/to/package" --check
```

Load `godot_package_resources` from the generated file and pass explicit dependencies,
resource paths of generated files and policy attributes from the hand-written BUILD.
This is source enumeration, not a Gazelle extension or automatic dependency
resolution. Both tools are optional.
