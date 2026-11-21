# autoload_gdunit

[GdUnit4](https://github.com/godot-gdunit-labs/gdUnit4) for Godot applications built with
[rules_godot](https://github.com/autoload-dev/rules_godot), as the Bazel module
`autoload_gdunit`: the GdUnit add-on and `gdunit_test`, which runs GdUnit suites as a Bazel
test.

| Target | What it is |
| --- | --- |
| `@autoload_gdunit//:gdunit` | The GdUnit4 add-on at `addons/gdUnit4`, test-only. Its editor part is the editor plugin and the scenes it docks. |
| `@autoload_gdunit//:defs.bzl%gdunit_test` | A `godot_test` whose main script is this module's GdUnit test adapter. |

## Use in an application

`MODULE.bazel` (see the [add-ons README](../README.md) for depending on a commit until the
module is on BCR):

```starlark
bazel_dep(name = "autoload_gdunit", version = "0.1.0", dev_dependency = True)
```

`BUILD.bazel`:

```starlark
load("@autoload_gdunit//:defs.bzl", "gdunit_test")
load("@autoload_rules_godot//godot:defs.bzl", "godot_resources")

godot_resources(
    name = "unit_suites",
    testonly = True,
    srcs = glob(["test/**/*_test.gd"]),
    deps = [":game", "@autoload_gdunit//:gdunit"],
)

gdunit_test(
    name = "unit_tests",
    project = ":project",
    suites = [":unit_suites"],
    shard_count = 4,
)
```

`gdunit_test` is a `godot_test` whose main script is this module's GdUnit test adapter, as
`py_pytest_test` is a `py_test` that runs pytest. A suite is a script of a `suites` target,
generated ones included, that extends GdUnit's `GdUnitTestSuite`, as GdUnit itself defines
one; helper scripts and sidecars beside the suites are none. The suites bring what they use
through their own `deps`, the GdUnit add-on included. Arguments after Godot's `--` in
`args`, and those from `--test_arg`, are GdUnit options. The test adapter

- runs only the suites whose `res://` path contains the `--test_filter` value,
- distributes those round-robin over `shard_count` shards,
- hands GdUnit's JUnit report to Bazel and keeps all its reports among the undeclared
  outputs under `gdunit/`,
- fails when a test fails or none runs, including when all are skipped, and when its
  `suites` hold no suite; a shard or `--test_filter` that leaves no suite passes,
- passes with orphan nodes, as GdUnit's command line does, and names the tests that left
  them in the log.

GdUnit's assertions provoke engine errors deliberately, so only its results decide.

`bazel test //path/to:unit_tests --test_filter=inventory_test` runs one suite. Bazel caches
a test target as a whole: split suites into several targets where a change should rerun
only some of them.

A `gdunit_test` runs every suite of its `suites` targets, so give each test environment its
own suites target, such as host unit suites and device integration suites. Where suites of
both environments use the same classes, move those classes into a third `godot_resources`
target that both depend on, as a Bazel package splits shared test helpers into a `testonly`
library. Keep the device test out of host runs with `tags = ["manual"]`:

```starlark
godot_resources(
    name = "test_support",
    testonly = True,
    srcs = glob(["test/support/**/*.gd"]),
    deps = [":game", "@autoload_gdunit//:gdunit"],
)

godot_resources(
    name = "unit_suites",
    testonly = True,
    srcs = glob(["test/unit/**/*_test.gd"]),
    deps = [":test_support"],
)

godot_resources(
    name = "device_suites",
    testonly = True,
    srcs = glob(["test/device/**/*_test.gd"]),
    deps = [":test_support"],
)

gdunit_test(name = "unit_tests", project = ":project", suites = [":unit_suites"])

gdunit_test(
    name = "device_tests",
    project = ":project",
    suites = [":device_suites"],
    tags = ["manual"],
)
```

## rules_godot version

`gdunit_test` builds on rules_godot's test adapter, `adapter_test` in
`@autoload_rules_godot//godot/private:adapter.bzl`. rules_godot lets other repositories load
it, but it is no supported API: each release of this module pins the rules_godot release
it works with. Use a rules_godot at least that new.

## Development

In this directory, `bazel test //...` runs the module's tests in `tests/`: GdUnit runs that
pass, fail, shard, filter and report the way Bazel's test encyclopedia requires, a pack with
GdUnit and the adapter in a project with strict warnings. `examples/` is an application that
consumes the module; `bazel test //...` there runs its suites. Both build against the rules
of this checkout. `mise run host:addon:gdunit` from the repository root runs both.
