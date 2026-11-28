"""EXPERIMENT(web-browser): ways to obtain rules_browsers' Chrome while the target is web."""

# The experiment reads the browser's files through rules_browsers' private provider; it has no public one.
# buildifier: disable=bzl-visibility
load("@rules_browsers//browsers/private:named_files_info.bzl", "NamedFilesInfo")

def _launcher_impl(ctx):
    browser = ctx.attr.browser
    if type(browser) == "list":
        browser = browser[0]
    binary = browser[NamedFilesInfo].value["CHROME-HEADLESS-SHELL"]
    out = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(
        out,
        "#!/bin/sh\nexec \"$0.runfiles/_main/../{}\" \"$@\"\n".format(
            binary.short_path.removeprefix("../"),
        ),
        is_executable = True,
    )
    return [DefaultInfo(
        executable = out,
        runfiles = ctx.runfiles([binary]).merge(browser[DefaultInfo].default_runfiles),
    )]

def _make_launcher(cfg):
    return rule(
        implementation = _launcher_impl,
        executable = True,
        attrs = {
            "browser": attr.label(
                cfg = cfg,
                default = "@rules_browsers//browsers/chromium:chromium",
                providers = [NamedFilesInfo],
            ),
        },
    )

# A: the browser as a tool of the execution platform.
exec_launcher = _make_launcher("exec")

# B: the browser in the target configuration, as rules_browsers' own test rules take it.
target_launcher = _make_launcher("target")

# C: an outgoing transition to the host platform.
def _to_host_impl(_settings, _attr):
    return {"//command_line_option:platforms": "@platforms//host"}

_to_host = transition(
    implementation = _to_host_impl,
    inputs = [],
    outputs = ["//command_line_option:platforms"],
)

host_launcher = rule(
    implementation = _launcher_impl,
    executable = True,
    attrs = {
        "browser": attr.label(
            cfg = _to_host,
            default = "@rules_browsers//browsers/chromium:chromium",
            providers = [NamedFilesInfo],
        ),
    },
)

# E: a toolchain per execution platform, resolved by the execution platform's constraints.
def _browser_toolchain_impl(ctx):
    return [platform_common.ToolchainInfo(browser = ctx.attr.browser)]

browser_toolchain = rule(
    implementation = _browser_toolchain_impl,
    attrs = {"browser": attr.label(cfg = "exec", providers = [NamedFilesInfo])},
)

def _toolchain_launcher_impl(ctx):
    toolchain = ctx.toolchains["//exp/browser:browser_toolchain_type"]
    if toolchain == None:
        out = ctx.actions.declare_file(ctx.label.name + ".sh")
        ctx.actions.write(out, "#!/bin/sh\necho 'no pinned browser for this host' >&2\nexit 2\n", is_executable = True)
        return [DefaultInfo(executable = out)]
    return _launcher_impl(struct(attr = struct(browser = toolchain.browser), label = ctx.label, actions = ctx.actions, runfiles = ctx.runfiles))

toolchain_launcher = rule(
    implementation = _toolchain_launcher_impl,
    executable = True,
    toolchains = [config_common.toolchain_type("//exp/browser:browser_toolchain_type", mandatory = False)],
)
