"""GdUnit4 as a godot_test main script, like a pytest driver over py_test."""

load("//godot/private:adapter.bzl", "adapter_test")

visibility("//godot/...")

def validate_suites(name, suites, _fail = fail):
    """
    Reject a godot_gdunit_test without suites.

    Args:
        name: Name of the godot_gdunit_test, for the failure message.
        suites: The suites argument.
        _fail: Reports the error; tests collect it instead of stopping.
    """
    if not suites:
        _fail("%s: godot_gdunit_test requires at least one suites target" % name)

def godot_gdunit_test(name, suites, **kwargs):
    """
    Run GdUnit4 test suites as a Bazel test.

    A godot_test whose main script is rules_godot's GdUnit test adapter. A suite is a
    script of the suites targets, generated ones included, that extends GdUnit's
    `GdUnitTestSuite`; helper scripts and sidecars beside the suites are none. The
    suites declare what they use in their deps: the code under test and GdUnit
    itself, pinned in your module like any other resources. The adapter follows
    Bazel's test contract: shard_count distributes the suites round-robin,
    `--test_filter` keeps the suites whose `res://` path contains it, the JUnit
    report becomes the test's XML result and all GdUnit reports appear among its
    undeclared outputs. The test fails when a test fails, when no test runs or when
    the suites targets hold no suite; a shard or `--test_filter` that leaves no
    suite passes. Orphan nodes fail no test, as GdUnit's command line judges them;
    the log names the tests that left them. GdUnit's assertions provoke engine
    errors deliberately, so only the exit code decides.

    Arguments after Godot's `--` in args, and those from `--test_arg`, are GdUnit
    options, as pytest receives a py_pytest_test's arguments.

    Example:
    ```starlark
    load("@autoload_rules_godot//godot/gdunit:defs.bzl", "godot_gdunit_test")

    godot_resources(
        name = "unit_suites",
        srcs = glob(["test/**/*_test.gd"]),
        deps = [":game", "@gdunit4"],
    )

    godot_gdunit_test(
        name = "unit_tests",
        project = ":project",
        suites = [":unit_suites"],
        shard_count = 4,
    )
    ```

    Run one suite with `bazel test :unit_tests --test_filter=inventory_test`. See
    [GdUnit tests](../../development.md#gdunit).

    ### Default outputs
    | kind | cardinality | availability | behavior |
    | --- | --- | --- | --- |
    | test | one | always | execute GdUnit suites under bazel test; JUnit reports are test outputs; editor/project are runfiles |

    ### Output groups
    none

    ### Generated targets
    none

    ### Providers
    none

    Args:
        name: Name of the test target.
        suites: godot_resources targets whose own files are the suites. Their deps
            bring what the suites use, including the pinned GdUnit add-on under
            addons/gdUnit4, helpers and fixtures; those files are not suites.
        **kwargs: godot_test arguments, such as args, project, size and
            shard_count.
    """
    validate_suites(name, suites)
    args = kwargs.pop("args", [])
    adapter_test(
        name = name,
        deps = suites,
        adapter = Label("//godot/gdunit/private:run.gd"),
        main = "addons/rules_godot_gdunit/run.gd",
        cases = "addons/rules_godot_gdunit/suites.txt",
        # Bazel appends --test_arg values, which then follow the separator too.
        kwargs = dict(kwargs, args = args if "--" in args else args + ["--"]),
    )
