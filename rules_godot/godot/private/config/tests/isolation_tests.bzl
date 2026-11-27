"""A desktop consumer's app needs no mobile toolchain and no input of an unselected signer."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot:app.bzl", "godot_app")
load("//godot:providers.bzl", "GodotDesktopAppInfo")
load("//godot/extension:defs.bzl", "godot_extension")
load("//godot/private/tests:fixture_files.bzl", "fixture_file")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

visibility("private")

_MODE = str(Label("//godot:macos_signing"))

_RUNTIMES = "//godot/private/config/tests/fixtures/desktop_runtimes_only"

# Desktop runtime components only: no Android or iOS runtime component is registered.
_DESKTOP_ONLY = own_toolchains([_RUNTIMES + ":all"])

_SMALL = {"size": "small"}

# The macOS application backend and its signer analyze with Apple toolchains of a macOS host.
_MACOS_HOST = _SMALL | {"target_compatible_with": ["@platforms//os:macos"]}

_MACOS = {"//command_line_option:platforms": str(Label("//godot/platforms:macos_arm64"))}

def _sign_actions(target):
    return [action for action in target[TestingAspectInfo].actions if action.mnemonic == "GodotMacosSign"]

def _arrange_app(name, **kwargs):
    godot_app(
        name = name + "_app",
        pack = kwargs.pop("pack", ":app_pack"),
        tags = ["manual"],
        **kwargs
    )

def _arrange_unresolvable_signing_input_app(name):
    # The entitlement label names no target: analyzing the signer fails on it.
    _arrange_app(name, macos_entitlements = ":" + name + "_missing_signing_input")

def _test_desktop_app_resolves_desktop_runtime_without_mobile_toolchains(name):
    _arrange_app(name)
    analysis_test(
        name = name,
        target = name + "_app",
        impl = _desktop_app_resolves_desktop_runtime_without_mobile_toolchains,
        # Unstripped, the app analyzes for a target platform whose C++ toolchain the
        # replaced registrations drop, such as Linux under --config=buildbuddy-linux.
        config_settings = _DESKTOP_ONLY | {"//command_line_option:strip": "never"},
        attr_values = _SMALL,
    )

def _desktop_app_resolves_desktop_runtime_without_mobile_toolchains(env, target):
    env.expect.that_bool(GodotDesktopAppInfo in target, expr = "GodotDesktopAppInfo in app").equals(True)
    if GodotDesktopAppInfo in target:
        component = target[GodotDesktopAppInfo].runtime_component
        env.expect.that_bool(component != None, expr = "the app names its runtime component").equals(True)
        if component:
            env.expect.that_str(component.component).contains(_RUNTIMES.removeprefix("//") + ":runtime_")

def _test_unsigned_app_reads_no_signing_input(name):
    _arrange_unresolvable_signing_input_app(name)
    analysis_test(
        name = name,
        target = name + "_app",
        impl = _unsigned_app_reads_no_signing_input,
        config_settings = _MACOS | _DESKTOP_ONLY | {_MODE: "unsigned"},
        attr_values = _MACOS_HOST,
    )

def _unsigned_app_reads_no_signing_input(env, target):
    env.expect.that_collection(_sign_actions(target), expr = "GodotMacosSign actions").has_size(0)
    owner = target[GodotDesktopAppInfo].bundle.owner
    env.expect.that_bool(owner.name.endswith("_app.macos"), expr = "bundle of the unsigned backend: " + str(owner)).equals(True)

def _test_certificate_debug_symbols_read_no_signing_input(name):
    _arrange_unresolvable_signing_input_app(name)
    analysis_test(
        name = name,
        target = name + "_app.debug_symbols",
        impl = _certificate_debug_symbols_read_no_signing_input,
        config_settings = _MACOS | _DESKTOP_ONLY | {_MODE: "certificate"},
        attr_values = _MACOS_HOST,
    )

def _certificate_debug_symbols_read_no_signing_input(env, target):
    files = target[DefaultInfo].files.to_list()
    env.expect.that_collection(files, expr = "debug symbols files").has_size(1)
    for file in files:
        env.expect.that_bool(".macos_signed" in file.owner.name, expr = "produced by the signer: " + str(file.owner)).equals(False)

def _test_certificate_mode_adds_no_signing_input_to_linux_app(name):
    _arrange_unresolvable_signing_input_app(name)
    analysis_test(
        name = name,
        target = name + "_app",
        impl = _certificate_mode_adds_no_signing_input_to_linux_app,
        # Unstripped, the Linux app analyzes on any host without a Linux C++ toolchain.
        config_settings = _DESKTOP_ONLY | {
            "//command_line_option:platforms": str(Label("//godot/platforms:linux_arm64")),
            "//command_line_option:strip": "never",
            _MODE: "certificate",
        },
        attr_values = _SMALL,
    )

def _certificate_mode_adds_no_signing_input_to_linux_app(env, target):
    env.expect.that_str(target[GodotDesktopAppInfo].operating_system).equals("linux")
    env.expect.that_collection(_sign_actions(target), expr = "GodotMacosSign actions").has_size(0)

def _test_invalid_signing_mode_fails(name):
    analysis_test(
        name = name,
        target = "//godot:macos_signing",
        impl = _invalid_signing_mode_fails,
        expect_failure = True,
        config_settings = {_MODE: "invalid"},
        attr_values = _SMALL,
    )

def _invalid_signing_mode_fails(env, target):
    env.expect.that_target(target).failures().contains_predicate(
        matching.contains("Error setting //godot:macos_signing: invalid value 'invalid'"),
    )

def _test_raw_pck_is_no_start_pack(name):
    """A pack target, not the PCK file it exports, supplies the start pack."""
    _arrange_app(name, pack = "fixtures/raw_pck/raw.pck")
    analysis_test(
        name = name,
        target = name + "_app",
        impl = _raw_pck_is_no_start_pack,
        expect_failure = True,
        config_settings = _DESKTOP_ONLY,
        attr_values = _SMALL,
    )

def _raw_pck_is_no_start_pack(env, target):
    env.expect.that_target(target).failures().contains_predicate(matching.contains("expected no files"))

def _test_extension_delegates_caller_private_labels(name):
    """Typed labels delegate the caller's private extension and platform libraries."""
    fixture_file(
        name = name + "_library",
        out = name + "/libprivate.so",
        visibility = ["//visibility:private"],
    )
    cc_library(
        name = name + "_platform_library",
        tags = ["manual"],
        visibility = ["//visibility:private"],
    )
    godot_extension(
        name = name + "_extension",
        entry_symbol = "fixture_init",
        library = select({"//conditions:default": ":" + name + "_library"}),
        platform_deps = select({"//conditions:default": [":" + name + "_platform_library"]}),
        tags = ["manual"],
        visibility = ["//visibility:private"],
    )
    analysis_test(
        name = name,
        target = name + "_extension",
        impl = _analyzes,
        attr_values = _SMALL,
    )

def _analyzes(env, target):
    """The target under test analyzes; the test asserts nothing else."""
    _ = (env, target)  # @unused

def isolation_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_desktop_app_resolves_desktop_runtime_without_mobile_toolchains,
            _test_unsigned_app_reads_no_signing_input,
            _test_certificate_debug_symbols_read_no_signing_input,
            _test_certificate_mode_adds_no_signing_input_to_linux_app,
            _test_invalid_signing_mode_fails,
            _test_raw_pck_is_no_start_pack,
            _test_extension_delegates_caller_private_labels,
        ],
    )
