"""EXPERIMENT(web tests), variant B: the browser as a toolchain of the test exec group."""

def _browser_toolchain_impl(ctx):
    return [platform_common.ToolchainInfo(
        chrome = ctx.file.chrome,
        files = depset(ctx.files.files),
    )]

browser_toolchain = rule(
    doc = "A pinned headless Chrome for one execution platform.",
    implementation = _browser_toolchain_impl,
    attrs = {
        "chrome": attr.label(allow_single_file = True, mandatory = True),
        "files": attr.label_list(allow_files = True),
    },
)

def _no_test_toolchain_impl(_ctx):
    return [platform_common.ToolchainInfo()]

# A default test toolchain implementation that is incompatible: tests of rules that keep
# Bazel's default "test" exec group then become incompatible on the web, instead of failing.
no_test_toolchain = rule(implementation = _no_test_toolchain_impl)

BROWSER_TOOLCHAIN = Label(":browser_toolchain_type")

def _web_browser_test_impl(ctx):
    browser = ctx.exec_groups["test"].toolchains[BROWSER_TOOLCHAIN]
    site = ctx.attr.app[OutputGroupInfo].bundle.to_list()[0]
    runner = ctx.attr._runner[DefaultInfo].files_to_run.executable
    args = ["--site", site.short_path, "--chrome", browser.chrome.short_path]
    for suite in ctx.attr.suites:
        args += ["--suite", suite]
    for arg in ctx.attr.godot_args:
        args.append("--godot-arg=" + arg)
    executable = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(
        executable,
        "#!/usr/bin/env bash\nexec {} {} \"$@\"\n".format(
            runner.short_path,
            " ".join(["'%s'" % arg for arg in args + ["--"] + ctx.attr.gdunit_args]),
        ),
        is_executable = True,
    )
    runfiles = ctx.runfiles(files = [site, browser.chrome], transitive_files = browser.files)
    runfiles = runfiles.merge(ctx.attr._runner[DefaultInfo].default_runfiles)
    return [DefaultInfo(executable = executable, runfiles = runfiles)]

web_browser_test = rule(
    doc = """
    Like //web_exp:defs.bzl's web_browser_test, but the "test" exec group is the rule's own:
    its browser toolchain chooses the execution platform and brings that platform's Chrome,
    so Bazel's default test toolchain does not apply to it.
    """,
    implementation = _web_browser_test_impl,
    test = True,
    exec_groups = {"test": exec_group(toolchains = [BROWSER_TOOLCHAIN])},
    attrs = {
        "app": attr.label(mandatory = True),
        "suites": attr.string_list(),
        "godot_args": attr.string_list(default = ["--audio-driver", "Dummy"]),
        "gdunit_args": attr.string_list(),
        "_runner": attr.label(
            default = Label("//web_exp:web_test_runner"),
            executable = True,
            cfg = config.exec("test"),
        ),
    },
)

def _trivial_test_impl(ctx):
    executable = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(executable, "#!/bin/sh\nexit 0\n", is_executable = True)
    return [DefaultInfo(executable = executable)]

# A test rule without toolchains of its own, standing for any other test rule.
trivial_test = rule(implementation = _trivial_test_impl, test = True)
