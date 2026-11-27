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

load("//godot/private:macros.bzl", "VOLATILE_API", "common_kwargs")
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

def _adapter_test_impl(name, visibility, deps, adapter, main, cases, tags, **kwargs):
    # Like the test and its view, the case helpers are test-only.
    common = common_kwargs(kwargs) | {
        "testonly": True,
        "tags": tags,
        "visibility": ["//visibility:private"],
    }
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
        visibility = visibility,
        deps = deps + [
            ":" + name + ".adapter",
            ":" + name + ".cases",
        ],
        main = main,
        tags = tags,
        # The adapter decides the outcome. Its cases provoke engine errors on
        # purpose, and stopping Godot after the first would cut its report short.
        engine_errors = "report",
        **kwargs
    )

adapter_test = macro(
    doc = """
    Declare a godot_test whose main script, a test adapter, runs the cases its deps list.

    The test contains the deps, the adapter's main script and rules_godot's case selection.
    The `res://` paths of the deps' own files, in path order, make up the case list at the
    resource path `cases`; the files of the deps' dependencies, such as the framework and
    the code under test, are none. The adapter decides which listed files are cases and
    the test's outcome: engine errors do not fail the test, since a framework provokes them
    on purpose. The macro declares the test `<name>` and its test-only helpers
    `<name>.case_list`, `<name>.cases` and `<name>.adapter`; every attribute of godot_test
    but pack and engine_errors works as there.

    Example, in a test framework module's macro:
    ```starlark
    adapter_test(
        name = name,
        deps = suites,
        adapter = Label("//my_framework:run.gd"),
        main = "addons/my_framework/run.gd",
        cases = "addons/my_framework/cases.txt",
        project = project,
    )
    ```
    """ + VOLATILE_API,
    implementation = _adapter_test_impl,
    inherit_attrs = godot_test,
    attrs = {
        "pack": None,
        "engine_errors": None,
        "deps": attr.label_list(
            doc = """
            godot_resources targets whose own files are the cases; their dependencies bring
            what the cases use, such as the framework and the code under test.
            """,
            providers = [GodotResourcesInfo],
            mandatory = True,
        ),
        "adapter": attr.label(
            doc = """
            The adapter's main script file. The test declares it as resources of its own,
            `<name>.adapter`, at the resource path `main`, which use the deps and the case
            selection.
            """,
            allow_single_file = True,
            mandatory = True,
            configurable = False,
        ),
        "main": attr.string(
            doc = "Resource path of the main script, such as `addons/my_framework/run.gd`.",
            mandatory = True,
            configurable = False,
        ),
        "cases": attr.string(
            doc = "Resource path of the case list the main script reads.",
            mandatory = True,
            configurable = False,
        ),
    },
)
