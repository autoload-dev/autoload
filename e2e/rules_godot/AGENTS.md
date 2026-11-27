# Ruleset regressions

This directory of the repository's root module holds the ruleset's consumer scenarios and
builds them as a consumer builds: through the root module's `MODULE.bazel`, with public
`@autoload_rules_godot` labels only. Where a new test goes is owned by the
[verification architecture](../../docs/internal/verification-architecture.md).

## Layout


| Location | Responsibility |
|---|---|
| `smoke/<operating_system>/` | The smoke path of one platform: its own project, extensions and checks, through public labels only |
| `script_run/`, `patched_engine/` | A focused consumer scenario named after what the user does, with its own project files and native fixtures |

## Common workflows

From the repository root, this runs every regression scenario that the host's toolchains
allow:

```sh
bazel test //e2e/rules_godot/...
```

The Android and iOS tests are tagged `android` and `ios`, and CI's Linux and macOS jobs
select them by tag (`--config=ci-linux`, `--config=ci-macos`); to run them alone, pass
`--test_tag_filters=android` or `--test_tag_filters=ios`. Their applications carry their
configuration (`godot_configured_app`), so they run without `--config`. The [fixture
catalogue](../../docs/internal/verification-recipes.md#mobile-artifact-checks) lists them.

For a reproducer or existing fixture, use the relevant entry in the
[fixture catalogue](../../docs/internal/verification-recipes.md#regression-fixtures) and run
its focused target from the repository root. The root verification policy owns TDD, timing and
evidence.

## Artifact test rules

To inspect a built Android App Bundle or iOS application, load `android_bundle_test` or
`ios_app_test` from `//tools/artifact_tests`, the root module's artifact test rules, and build
a mobile application under its own configuration with `godot_configured_app` from
`@autoload_rules_godot//godot:app.bzl`. A scenario loads nothing from a `private` package of the
ruleset ([B3](../../docs/internal/verification-architecture.md#boundary-rules)). The ruleset offers no other test labels: a scenario owns its project files,
native fixtures and inspectors.

## Fixture scope

Keep project-specific assertions and drivers with their case; keep all regression inputs
independent of examples. C++ test-input libraries do not need artificial add-on/demo
projects. A project's mobile applications package that project; a case that needs another
project's files gets a focused project of its own. When moving resources, update runtime
paths, authored sidecars and assertions together; retain explicit resource paths when the
resource path itself is the regression.
