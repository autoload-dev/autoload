"""EXPERIMENT(web tests): a test rule that runs a web godot_app in the pinned headless Chrome."""

def _web_browser_test_impl(ctx):
    site = ctx.attr.app[OutputGroupInfo].bundle.to_list()[0]
    runner = ctx.attr._runner[DefaultInfo].files_to_run.executable
    chrome = ctx.file._chrome
    args = ["--site", site.short_path, "--chrome", chrome.short_path]
    for suite in ctx.attr.suites:
        args += ["--suite", suite]
    for arg in ctx.attr.godot_args:
        args.append("--godot-arg=" + arg)
    args += ["--"] + ctx.attr.gdunit_args
    executable = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(
        executable,
        "#!/usr/bin/env bash\nexec {runner} {args} \"$@\"\n".format(
            runner = runner.short_path,
            args = " ".join(["'%s'" % arg for arg in args]),
        ),
        is_executable = True,
    )
    runfiles = ctx.runfiles(files = [site, chrome] + ctx.files._chrome_files)
    runfiles = runfiles.merge(ctx.attr._runner[DefaultInfo].default_runfiles)
    return [DefaultInfo(executable = executable, runfiles = runfiles)]

web_browser_test = rule(
    doc = """
    Run a web godot_app's GdUnit suites in headless Chrome. The app is built for the target
    platform (web); the runner and Chrome are built for the test's execution platform
    (exec group "test"), which a toolchain of default_test_toolchain_type chooses.
    """,
    implementation = _web_browser_test_impl,
    test = True,
    attrs = {
        "app": attr.label(mandatory = True),
        "suites": attr.string_list(),
        "godot_args": attr.string_list(default = ["--audio-driver", "Dummy"]),
        "gdunit_args": attr.string_list(),
        "_runner": attr.label(
            default = Label(":web_test_runner"),
            executable = True,
            cfg = config.exec("test"),
        ),
        "_chrome": attr.label(
            default = Label(":chrome"),
            allow_single_file = True,
            cfg = config.exec("test"),
        ),
        "_chrome_files": attr.label(
            default = Label(":chrome_files"),
            cfg = config.exec("test"),
        ),
    },
)
