# Ruleset regressions

This independent Bazel module, `rules_godot_tests`, holds the ruleset's regression
projects and builds them as a consumer builds: through its own `MODULE.bazel`, with public
`@autoload_rules_godot` labels only. This page describes the module as it exists. Where a new test
goes, and what this module will contain, is owned by the
[verification architecture](../../docs/internal/verification-architecture.md).

## Layout


| Location | Responsibility |
|---|---|
| `smoke/<operating_system>/` | The smoke path of one platform: its own project, extensions and checks, through public labels only |
| `shared_addon/`, `script_run/`, `patched_engine/` | A focused consumer scenario named after what the user does, with its own project files and native fixtures |
| `BUILD.bazel` | The Maven lock exports and the configuration suites |

## Common workflows

From this directory, the host set runs every regression that needs no Android or Apple
device toolchain:

```sh
bazel test //...
```

`mise run work -- test:regressions` runs the same from the repository root without the Android SDK, as CI does. Android and iOS tests
are `manual` and run in configuration suites: `test_suite` targets in `BUILD.bazel`, one per
`.bazelrc` configuration, run with that `--config`. The `android` and `ios` work of
their lanes runs them; the
[fixture catalogue](../../docs/internal/verification-recipes.md#mobile-artifact-checks)
lists the suites.

For a reproducer or existing fixture, use the relevant entry in the
[fixture catalogue](../../docs/internal/verification-recipes.md#regression-fixtures) and run
its focused target from this directory. The root verification policy owns TDD, timing and
evidence.

## Artifact test rules

To inspect a built Android App Bundle or iOS application, load `android_bundle_test` or
`ios_app_test` from `@autoload_rules_godot//godot/private/testing`, with
`# buildifier: disable=bzl-visibility`. They are the ruleset's own test rules, not
supported API. The ruleset offers no other test labels: a scenario owns its project files,
native fixtures and inspectors.

## Fixture scope

Keep project-specific assertions and drivers with their case; keep all regression inputs
independent of examples. C++ test-input libraries do not need artificial add-on/demo
projects. A project's mobile applications package that project; a case that needs another
project's files gets a focused project of its own. When moving resources, update runtime
paths, authored sidecars and assertions together; retain explicit resource paths when the
resource path itself is the regression.
