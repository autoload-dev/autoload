# Maintainer tools

This guide covers the resource-graph query; Godot BUILD declarations come from Gazelle.
Run its commands from `rules_godot/`. For repository checks and timing, read the
[verification policy](../../../docs/internal/verification.md); for a fixture or environment
setup, use the relevant [verification recipe](../../../docs/internal/verification-recipes.md).
For application execution, content validation, GdUnit, editor views and sidecars, see
[development and testing](../public/development.md).

## Analysis and BUILD maintenance

`godot_resource_graph` in `godot/private/analysis.bzl` writes a project's resource graph
for the ruleset's own tests; the scanner scope is described in
[detected references](../public/resources.md#detected-references).
Maintainers can query a test fixture's graph with the repository tool:

```sh
bazel build //godot/private/tests/resource_graph/fixtures/declared_project:graph
bazel run //tools:resource_graph -- query \
  --graph "$PWD/bazel-bin/godot/private/tests/resource_graph/fixtures/declared_project/graph.graph.json" \
  --direction affected res://main/content.tres
```

Queries support reachability and reverse affected-file closure; supplying
`--previous-graph` includes deleted or changed old edges. With a previous graph,
affected UID queries include the previous and current owners of a moved stable UID;
reachability prefers its current owner. These are conservative file graphs, not automatic
Bazel target selection.

The repository's Gazelle language for Godot generates the declarations of Godot projects,
resources and GdUnit tests; see [Gazelle for Godot](../../../docs/internal/gazelle.md).
