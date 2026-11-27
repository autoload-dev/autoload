"""Test what an iOS application contains, without running it."""

load("@rules_apple//apple:providers.bzl", "AppleBundleInfo")

def _runfile_key(ctx, short_path):
    # The path below a runfiles directory; those of external files start with ../.
    if short_path.startswith("../"):
        return short_path[3:]
    return ctx.workspace_name + "/" + short_path

def _ios_app_test_impl(ctx):
    bundle = ctx.attr.app[AppleBundleInfo].archive
    inspector = ctx.attr._inspector[DefaultInfo].files_to_run.executable
    flags = [("--symbol", value) for value in ctx.attr.symbols]
    flags += [("--file", value) for value in ctx.attr.files]
    flags += [("--infoplist-key", value) for value in ctx.attr.infoplist_keys]
    arguments = [
        "  %s '%s' \\" % (flag, value.replace("'", "'\\''"))
        for flag, value in flags
    ]
    if ctx.attr.debug_symbols:
        arguments.append("  --dsym-required \\")
        arguments += [
            '  --dsym "$runfiles/%s" \\' % _runfile_key(ctx, file.short_path)
            for file in ctx.files.debug_symbols
        ]
    if not arguments:
        fail(
            "ios_app_test needs at least one of symbols, files, infoplist_keys " +
            "or debug_symbols",
        )
    launcher = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.expand_template(
        template = ctx.file._launcher_template,
        output = launcher,
        substitutions = {
            "{INSPECTOR}": _runfile_key(ctx, inspector.short_path),
            "{APP}": _runfile_key(ctx, bundle.short_path),
            "{ARGUMENTS}": "\n".join(arguments),
        },
        is_executable = True,
    )
    runfiles = ctx.runfiles(files = [bundle] + ctx.files.debug_symbols)
    runfiles = runfiles.merge(ctx.attr._inspector[DefaultInfo].default_runfiles)
    return [DefaultInfo(executable = launcher, runfiles = runfiles)]

ios_app_test = rule(
    doc = """
    Test what an iOS application contains, without a simulator or device.

    The test reads the application's `.app` directory or unpacks its `.ipa` and checks
    that its executable defines every listed C symbol, local ones included, that every
    listed file exists in the bundle and that its `Info.plist` has every listed key.
    With `debug_symbols`, the application's dSYM must exist and carry the executable's
    UUID for each CPU. The test fails with the list of what the application lacks; at
    least one check must be requested.

    A statically linked extension shows as its entry symbol, such as the
    `entry_symbol` of godot_cc_extension. The inspection uses Apple's `nm`, so it runs
    on a macOS execution platform with Xcode; see [iOS](../../platforms.md#ios).

    Example:
    ```starlark
    ios_app_test(
        name = "app_links_extension_test",
        app = ":app",
        symbols = ["game_native_init"],
        infoplist_keys = ["CFBundleShortVersionString"],
    )
    ```
    """,
    implementation = _ios_app_test_impl,
    attrs = {
        "app": attr.label(
            doc = "The iOS application to test: a godot_app built for an iOS export platform, or another target providing rules_apple's AppleBundleInfo.",
            mandatory = True,
            providers = [AppleBundleInfo],
        ),
        "symbols": attr.string_list(
            doc = "C symbol names the executable must define, without the leading underscore of Mach-O symbols, such as `native_counter_init`.",
        ),
        "files": attr.string_list(
            doc = "Paths relative to the `.app` bundle that must exist, such as a bundled resource file.",
        ),
        "infoplist_keys": attr.string_list(
            doc = "Keys the application's `Info.plist` must contain, such as a usage description an add-on adds.",
        ),
        "debug_symbols": attr.label(
            doc = """
            The application's `<name>.debug_symbols`, whose dSYM must carry the
            executable's UUIDs. Build with `--apple_generate_dsym`; unset, the test
            checks no dSYM.
            """,
        ),
        "_launcher_template": attr.label(
            default = Label("//tools/artifact_tests:ios_app_test.sh.tpl"),
            allow_single_file = True,
        ),
        "_inspector": attr.label(
            default = Label("//tools/artifact_tests:inspect_ios_app"),
            executable = True,
            cfg = config.exec("test"),
        ),
    },
    # The inspection uses Apple's tools, so it runs on a macOS execution platform,
    # never on the iOS target platform.
    exec_groups = {"test": exec_group(exec_compatible_with = ["@platforms//os:osx"])},
    test = True,
)
