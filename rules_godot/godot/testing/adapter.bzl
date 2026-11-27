"""
Build a test framework's Bazel test on godot_test: `adapter_test` runs the framework's test
adapter over the cases its deps list.

A test adapter is a main script that runs a test framework under Bazel's test contract. It
reads the case list, a file of the cases' `res://` paths, and passes the path to rules_godot's
case selection, `res://addons/rules_godot_test/cases.gd`, which keeps the cases of this shard
and of `--test_filter`; the adapter then runs them, writes its reports and exits with the
test's result. autoload_gdunit's `gdunit_test` is a test adapter for GdUnit4.

Volatile API: public, but it may still change incompatibly in a release of rules_godot. A
module that builds on it pins the rules_godot release it works with.
"""

load("//godot/private:macros.bzl", "common_kwargs")
load("//godot/private:providers.bzl", "GodotResourcesInfo")
load("//godot/private:resources.bzl", "godot_resources", "own_paths")
load("//godot/private:run.bzl", "godot_test")

def _case_list_impl(ctx):
    cases = sorted({
        path: True
        for target in ctx.attr.deps
        for path in own_paths(target[GodotResourcesInfo])
    })
    if not cases:
        fail("%s: deps contain no file" % ctx.label)
    output = ctx.outputs.out
    ctx.actions.write(output, "".join(["res://%s\n" % path for path in cases]))
    return [DefaultInfo(files = depset([output]))]

_case_list = rule(
    doc = "Write the `res://` paths of a test adapter's cases, one per line.",
    implementation = _case_list_impl,
    attrs = {
        "deps": attr.label_list(providers = [GodotResourcesInfo]),
    },
    # Loading-time tools can classify this as generated resource content before
    # the adapter has been analyzed or built.
    outputs = {"out": "%{name}.txt"},
)

def adapter_test(name, deps, adapter, main, cases, kwargs):
    """
    Declare a godot_test whose main script, a test adapter, runs the cases its deps list.

    The test contains the deps, the adapter's main script and rules_godot's case selection.
    The `res://` paths of the deps' own files, in path order, make up the case list at the
    resource path `cases`; the files of the deps' dependencies, such as the framework and
    the code under test, are none. The adapter decides which listed files are cases and
    the test's outcome: engine errors do not fail the test, since a framework provokes them
    on purpose. The test and its helpers `<name>.case_list`, `<name>.cases` and
    `<name>.adapter` are test-only.

    Volatile API: public, but it may still change incompatibly in a release of rules_godot.
    A module that builds on it pins the rules_godot release it works with.

    Example, in a test framework module's macro:
    ```starlark
    adapter_test(
        name = name,
        deps = suites,
        adapter = Label("//my_framework:run.gd"),
        main = "addons/my_framework/run.gd",
        cases = "addons/my_framework/cases.txt",
        kwargs = kwargs,
    )
    ```

    Args:
        name: Name of the test target.
        deps: The test's deps, whose own files are the cases, in path order; the
            files of their dependencies are none.
        adapter: The adapter's main script file, which the test declares as resources of
            its own, `<name>.adapter`, that use the deps and the shared case selection,
            for a script that uses what the deps bring, such as GdUnit.
        main: Resource path of the main script.
        cases: Resource path of the case list the main script reads.
        kwargs: Remaining godot_test arguments.
    """
    if any([key in kwargs for key in ["main", "pack", "engine_errors"]]):
        fail("%s: this test sets its own main script" % name)

    # Like godot_test's own view, the case helpers are test-only.
    kwargs = dict(kwargs, testonly = kwargs.get("testonly", True))
    common = dict(common_kwargs(kwargs), visibility = ["//visibility:private"])
    _case_list(
        name = name + ".case_list",
        deps = deps,
        **common
    )
    godot_resources(
        name = name + ".cases",
        resource_paths = {":" + name + ".case_list": cases},
        **common
    )
    godot_resources(
        name = name + ".adapter",
        resource_paths = {adapter: main},
        deps = deps + [Label("//godot/testing:test_cases")],
        **common
    )
    godot_test(
        name = name,
        deps = deps + [
            ":" + name + ".adapter",
            ":" + name + ".cases",
        ],
        main = main,
        # The adapter decides the outcome. Its cases provoke engine errors on
        # purpose, and stopping Godot after the first would cut its report short.
        engine_errors = "report",
        **kwargs
    )
