"""
The rules of a checkout writer: `bazel run` writes files into the checkout and its test checks them.

A checkout writer keeps files the build derives, such as a project's sidecars or a runtime
profile, in version control. Its writer target runs a Python runner with a manifest of what
the build derived; its test target runs the same runner with `test` set, so `bazel test`
fails while the checkout differs. godot_metadata_sync and godot_runtime_profile share the
rule arguments, the launcher and the macro's target declarations.

Sections: Rule arguments, Launcher, Targets.
"""

load("//godot/private:execution.bzl", "EDITORLESS_RUN_EXEC_GROUPS", "EDITORLESS_TEST_EXEC_GROUPS", "RUN_EXEC_GROUPS", "TEST_EXEC_GROUPS")
load("//godot/private:run.bzl", "launcher")

visibility("//godot/...")

# ==== Rule arguments ==========================================================

def sync_rules(implementation, runner, attrs, docs, editor, cfg = None):
    """
    Return the arguments of `rule()` for a checkout writer and for its test.

    Rules take them as `rule(**arguments.writer)` and `rule(**arguments.test)`, bound to
    global names, so macros can instantiate them.

    Args:
        implementation: Function of (ctx, test) that returns the rule's providers, usually
            through sync_launcher; test is True for the test.
        runner: Label of the Python runner both targets run.
        attrs: The rules' attributes besides `writer`, the writer's label that the test's
            report names, and the launcher template and runner.
        docs: The documentation of the writer rule and of the test rule, as a pair.
        editor: Whether the runner starts the editor, so both targets resolve its
            toolchain; the runners that only compare and copy files need none.
        cfg: The rules' incoming transition, or None.

    Returns:
        A struct of the dicts `writer` and `test`.
    """

    def runner_attr(group):
        return {"_runner": attr.label(default = runner, executable = True, cfg = config.exec(group))}

    run_groups = RUN_EXEC_GROUPS if editor else EDITORLESS_RUN_EXEC_GROUPS
    test_groups = TEST_EXEC_GROUPS if editor else EDITORLESS_TEST_EXEC_GROUPS
    return struct(
        writer = dict(
            doc = docs[0],
            implementation = lambda ctx: implementation(ctx, False),
            attrs = _ATTRS | attrs | runner_attr("run"),
            executable = True,
            exec_groups = run_groups,
            cfg = cfg,
        ),
        test = dict(
            doc = docs[1],
            implementation = lambda ctx: implementation(ctx, True),
            attrs = _ATTRS | attrs | runner_attr("test"),
            test = True,
            exec_groups = test_groups,
            cfg = cfg,
        ),
    )

_ATTRS = {
    "writer": attr.string(),
    "_launcher_template": attr.label(
        default = Label("//godot/private:run_launcher.sh.tpl"),
        allow_single_file = True,
    ),
}

# ==== Launcher ================================================================

def sync_launcher(ctx, test, data, runfiles):
    """
    Write the manifest and launcher of a checkout writer's runner, and return its providers.

    Args:
        ctx: Analysis context of a rule made with sync_rules.
        test: Whether the target is the test, which checks instead of writing.
        data: The manifest's content besides the fields every runner reads: the workspace,
            `test` and the writer's label.
        runfiles: The runfiles the runner needs besides its manifest and runner.

    Returns:
        A list of DefaultInfo with the launcher as its executable.
    """
    executable, manifest = launcher(ctx, dict(
        data,
        workspace = ctx.workspace_name,
        test = test,
        writer = ctx.attr.writer,
    ))
    runfiles = runfiles.merge(ctx.runfiles(files = [manifest, ctx.executable._runner]))
    runfiles = runfiles.merge(ctx.attr._runner[DefaultInfo].default_runfiles)
    return [DefaultInfo(executable = executable, runfiles = runfiles)]

# ==== Targets =================================================================

# The size and timeout of a writer's test, `<name>.test`, as macro attributes.
TEST_SIZE_ATTRS = {
    "size": attr.string(
        doc = "Bazel test size of `<name>.test`; Bazel's default applies when unset.",
        values = ["", "small", "medium", "large", "enormous"],
        configurable = False,
    ),
    "timeout": attr.string(
        doc = "Bazel test timeout of `<name>.test`; derived from size when unset.",
        values = ["", "short", "moderate", "long", "eternal"],
        configurable = False,
    ),
}

def declare_sync(rules, name, attrs, test_attrs, kwargs):
    """
    Declare a checkout writer and its test, `<name>.test`.

    Args:
        rules: A struct of the exported rules `writer` and `test`.
        name: Name of the writer.
        attrs: The attributes both targets share, such as their view.
        test_attrs: The attributes of the test only: its size and timeout.
        kwargs: The macro's common attributes, such as tags and visibility.
    """
    writer = str(native.package_relative_label(name))
    rules.writer(name = name, writer = writer, **(attrs | kwargs))
    rules.test(name = name + ".test", writer = writer, **(test_attrs | attrs | kwargs))
