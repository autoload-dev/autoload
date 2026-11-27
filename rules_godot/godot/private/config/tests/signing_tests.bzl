"""Selected macOS signing modes, declared inputs and failure boundaries."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot:providers.bzl", "GodotDesktopAppInfo")

visibility("private")

_MODE = str(Label("//godot:macos_signing"))

_MACOS_HOST = {
    "size": "small",
    "target_compatible_with": ["@platforms//os:macos"],
}

def _selected_signing_test(name, mode, identity):
    analysis_test(
        name = name,
        target = ":signing_app",
        impl = _selected_signing_signs_declared_inputs,
        attrs = {"identity": attr.string()},
        config_settings = {_MODE: mode},
        attr_values = _MACOS_HOST | {"identity": identity},
    )

def _selected_signing_signs_declared_inputs(env, target):
    app = target[GodotDesktopAppInfo]
    actions = [action for action in target[TestingAspectInfo].actions if action.mnemonic == "GodotMacosSign"]
    env.expect.that_collection(actions, expr = "GodotMacosSign actions").has_size(1)
    if actions:
        argv = actions[0].argv
        env.expect.that_str(argv[argv.index("--identity") + 1]).equals(env.ctx.attr.identity)
        env.expect.that_collection(actions[0].inputs.to_list(), expr = "signing inputs").contains_predicate(
            matching.file_basename_equals("generated.entitlements"),
        )
    env.expect.that_str(app.archive.basename).equals("signing_app.zip")
    env.expect.that_str(app.executable_path).equals("Contents/MacOS/signing_app")
    env.expect.that_str(target[DefaultInfo].files_to_run.executable.basename).equals("signing_app.run")
    env.expect.that_collection(target[DefaultInfo].default_runfiles.files.to_list(), expr = "runfiles").contains(app.bundle)
    env.expect.that_bool(hasattr(target[OutputGroupInfo], "_validation"), expr = "has _validation output group").equals(True)

def _test_adhoc_signing_signs_with_dash_identity(name):
    _selected_signing_test(name, "adhoc", "-")

def _test_certificate_signing_signs_with_app_identity(name):
    _selected_signing_test(name, "certificate", "analysis-only certificate")

def _test_certificate_signing_without_identity_fails(name):
    analysis_test(
        name = name,
        target = ":app",
        impl = _certificate_signing_without_identity_fails,
        expect_failure = True,
        config_settings = {_MODE: "certificate"},
        attr_values = _MACOS_HOST,
    )

def _certificate_signing_without_identity_fails(env, target):
    env.expect.that_target(target).failures().contains_predicate(
        matching.contains("certificate mode requires a nonempty macos_signing_identity other than '-'"),
    )

def _test_debug_symbols_need_no_signing_identity(name):
    analysis_test(
        name = name,
        target = ":app.debug_symbols",
        impl = _debug_symbols_need_no_signing_identity,
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/platforms:macos_arm64")),
            _MODE: "certificate",
        },
        attr_values = _MACOS_HOST,
    )

def _debug_symbols_need_no_signing_identity(env, target):
    files = target[DefaultInfo].files.to_list()
    env.expect.that_collection(files, expr = "debug symbols files").has_size(1)
    if files:
        env.expect.that_bool(files[0].basename.endswith("_debug_symbols.zip"), expr = "ends with _debug_symbols.zip").equals(True)

def signing_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_adhoc_signing_signs_with_dash_identity,
            _test_certificate_signing_signs_with_app_identity,
            _test_certificate_signing_without_identity_fails,
            _test_debug_symbols_need_no_signing_identity,
        ],
    )
