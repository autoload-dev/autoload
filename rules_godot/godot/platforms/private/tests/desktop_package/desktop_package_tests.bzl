"""
The runtime contract of desktop packaging and the native code in a desktop package.

A desktop backend packages its runtime's executable and declared files; it checks the
runtime's operating system and executable, never its version or variant. Bazel's --strip
decides which native code the package strips; the debug symbols hold it unstripped.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot/platforms/private/tests:backends.bzl", "godot_linux_application")
load("//godot/private/tests:action_inputs.bzl", "godot_actions", "mapped_cache_keys")

visibility("private")

_RUNTIMES = "//godot/platforms/private/tests/desktop_package/fixtures/desktop_runtimes_without_engine:"
_MACOS_APP = "//godot/platforms/private/tests/desktop_package/fixtures/macos_app_from_project:"
_SYMBOLS = "//godot/platforms/private/tests/desktop_package/fixtures/apps_with_native_symbols:"
_DSYMS = "//godot/platforms/private/tests/desktop_package/fixtures/macos_apps_with_dsyms:"
_ICON = "//godot/platforms/private/tests/desktop_package/fixtures/macos_app_with_liquid_glass_icon:"
_SHARED = "//godot/platforms/private/tests/desktop_package/fixtures/host_test_and_macos_app:"

_SMALL = {"size": "small"}

# .dSYMs come from Apple's linker and dsymutil.
_MACOS_HOST = {"size": "small", "target_compatible_with": ["@platforms//os:macos"]}

def _linux_app(name, pack, runtime):
    godot_linux_application(
        name = name,
        pack = pack,
        runtime = runtime,
        tags = ["manual"],
    )
    return ":" + name

def _analyzes(_env, _target):
    pass

def _analyzes_test(name, pack, runtime):
    analysis_test(
        name = name,
        target = _linux_app(name + "_app", pack, runtime),
        impl = _analyzes,
        attr_values = _SMALL,
    )

def _fails_test(name, pack, runtime, message):
    analysis_test(
        name = name,
        target = _linux_app(name + "_app", pack, runtime),
        impl = _fails_with_message,
        expect_failure = True,
        attrs = {"message": attr.string()},
        attr_values = _SMALL | {"message": message},
    )

def _fails_with_message(env, target):
    env.expect.that_target(target).failures().contains_predicate(
        matching.contains(env.ctx.attr.message),
    )

# application/liquid_glass_icon resolves as the resource graph does and must name a directory.

def _test_liquid_glass_icon_naming_a_file_fails(name):
    analysis_test(
        name = name,
        target = _ICON + "app_naming_a_file",
        impl = _fails_with_message,
        expect_failure = True,
        attrs = {"message": attr.string()},
        attr_values = _MACOS_HOST | {
            "message": "application/liquid_glass_icon names res://game.icon/icon.json, which is a file, not an Icon Composer .icon directory",
        },
    )

# Editor and runtime are independent: neither a newer nor an older runtime is compared with
# the editor that exported the pack, and the runtime toolchain alone selects the variant.

def _test_newer_runtime_than_editor_analyzes(name):
    _analyzes_test(name, _RUNTIMES + "pack", _RUNTIMES + "beta_runtime")

def _test_older_runtime_than_editor_analyzes(name):
    _analyzes_test(name, _RUNTIMES + "beta_editor_pack", _RUNTIMES + "linux_runtime")

def _test_debug_runtime_variant_analyzes(name):
    _analyzes_test(name, _RUNTIMES + "pack", _RUNTIMES + "debug_runtime")

# What a runtime must be.

def _test_runtime_without_runtime_info_fails(name):
    _fails_test(
        name,
        _RUNTIMES + "pack",
        _RUNTIMES + "raw_runtime",
        "does not have mandatory providers: 'GodotRuntimeInfo'",
    )

def _test_runtime_source_file_fails(name):
    _fails_test(name, _RUNTIMES + "pack", _RUNTIMES + "runtime.sh", "expected no files")

def _test_runtime_of_other_operating_system_fails(name):
    _fails_test(
        name,
        _RUNTIMES + "pack",
        _RUNTIMES + "macos_runtime",
        "macos runtime cannot package a linux app",
    )

def _test_runtime_without_executable_fails(name):
    _fails_test(
        name,
        _RUNTIMES + "pack",
        _RUNTIMES + "library_runtime",
        "desktop runtime must provide an executable",
    )

# The packaging action reads the runtime's executable, its declared files and, for macOS,
# the shell files.

def _packaging_reads_test(name, target, inputs):
    analysis_test(
        name = name,
        target = target,
        impl = _packaging_reads,
        attrs = {"inputs": attr.string_list()},
        attr_values = _SMALL | {"inputs": inputs},
    )

def _packaging_reads(env, target):
    actions = [
        action
        for action in target[TestingAspectInfo].actions
        if action.mnemonic == "GodotDesktopPackage"
    ]
    env.expect.that_collection(actions, expr = "GodotDesktopPackage actions").has_size(1)
    if actions:
        env.expect.that_collection(
            [file.basename for file in actions[0].inputs.to_list()],
            expr = "GodotDesktopPackage inputs",
        ).contains_at_least(env.ctx.attr.inputs)

def _test_linux_packaging_reads_runtime_files(name):
    _packaging_reads_test(name, _RUNTIMES + "linux_app", ["runtime.sh", "runtime_support.txt"])

def _test_macos_packaging_reads_runtime_and_shell_files(name):
    _packaging_reads_test(
        name,
        _MACOS_APP + "app",
        ["runtime.sh", "runtime_support.txt", "Info.plist", "PrivacyInfo.xcprivacy"],
    )

# A host test and a macOS application validate each unit with one cache key: the test runs
# in the editor variant, and path mapping removes the configuration from the validation's
# paths; the project context resets the macOS minimum version the application's edge to its
# pack sets, which would otherwise reach the unit's inputs.
def _test_host_test_and_macos_app_share_validations(name):
    analysis_test(
        name = name,
        targets = {
            "app": _SHARED + "app",
            "test": _SHARED + "test",
        },
        impl = _host_test_and_macos_app_share_validations,
        extra_target_under_test_aspects = [godot_actions],
        attr_values = _SMALL,
    )

def _host_test_and_macos_app_share_validations(env, targets):
    for unit in ["base", "main"]:
        keys = {}
        for subject in ["app", "test"]:
            reached = [
                facts
                for (owner, _, _), facts in mapped_cache_keys(getattr(targets, subject), ["GodotValidate"]).items()
                if owner.endswith(":" + unit)
            ]
            env.expect.where(unit = unit, operation = subject).that_collection(reached).has_size(1)
            keys.update({facts: True for facts in reached})
        env.expect.where(unit = unit).that_collection(keys.keys()).has_size(1)

# The debug symbols of a Linux application, with stripping as Bazel's --strip decides: by
# default (sometimes) in fastbuild only.

_STRIPPABLE = [
    "Game",
    "native/bin/{tags}/libandroid_library_fixture.so",
]

def _tagless(path):
    """Replace the feature tags of an extension library's directory, which the configuration derives."""
    head, separator, tail = path.partition("native/bin/")
    if not separator:
        return path
    return head + separator + "{tags}/" + tail.partition("/")[2]

def _symbols_test(name, stripped, config_settings = {}):
    analysis_test(
        name = name,
        target = _SYMBOLS + "app",
        impl = _strips_and_keeps_debug_symbols,
        attrs = {"stripped": attr.bool()},
        config_settings = config_settings,
        attr_values = _SMALL | {"stripped": stripped},
    )

def _debug_symbol_entries(env, target):
    """Return the destination and source entries of the application's debug symbol ZIP."""
    archive = target[OutputGroupInfo].debug_symbols.to_list()[0].short_path
    manifests = [
        action
        for action in target[TestingAspectInfo].actions
        if action.mnemonic == "FileWrite" and
           action.outputs.to_list()[0].short_path.endswith(archive + ".json")
    ]
    env.expect.that_collection(manifests, expr = "debug symbol manifests").has_size(1)
    return json.decode(manifests[0].content) if manifests else []

def _strips_and_keeps_debug_symbols(env, target):
    prefix = target.label.name + "_stripped/"
    env.expect.that_collection(
        [
            _tagless(file.short_path.split(prefix, 1)[1])
            for action in target[TestingAspectInfo].actions
            if action.mnemonic == "GodotStrip"
            for file in action.outputs.to_list()
        ],
        expr = "stripped files",
    ).contains_exactly(_STRIPPABLE if env.ctx.attr.stripped else [])
    entries = _debug_symbol_entries(env, target)
    env.expect.that_collection(
        [_tagless(entry["destination"]) for entry in entries],
        expr = "debug symbol paths",
    ).contains_exactly(_STRIPPABLE)
    for entry in entries:
        env.expect.where(destination = entry["destination"]).that_bool(
            prefix in entry["source"],
            expr = "debug symbols are the stripped file",
        ).equals(False)
    env.expect.that_collection(
        [file.basename for file in target[OutputGroupInfo].debug_symbols.to_list()],
        expr = "debug_symbols output group",
    ).contains_exactly(["Game_debug_symbols.zip"])

def _test_fastbuild_strips_native_code(name):
    _symbols_test(
        name,
        stripped = True,
        config_settings = {
            "//command_line_option:compilation_mode": "fastbuild",
            "//command_line_option:strip": "sometimes",
        },
    )

def _test_opt_keeps_native_code_unstripped(name):
    _symbols_test(
        name,
        stripped = False,
        config_settings = {"//command_line_option:compilation_mode": "opt"},
    )

def _test_strip_always_strips_native_code_in_opt(name):
    _symbols_test(
        name,
        stripped = True,
        config_settings = {
            "//command_line_option:compilation_mode": "opt",
            "//command_line_option:strip": "always",
        },
    )

def _test_strip_never_keeps_native_code_unstripped(name):
    _symbols_test(
        name,
        stripped = False,
        config_settings = {"//command_line_option:strip": "never"},
    )

# On macOS, the debug symbols of native code rules_cc links with --apple_generate_dsym are
# the .dSYMs its linker wrote, with the DWARF of the object files; dsymutil extracts one
# from other files.

def _dsyms_test(name, target, extracted, linked):
    analysis_test(
        name = name,
        target = target,
        impl = _dsyms_are_linked_or_extracted,
        attrs = {
            "extracted": attr.string_list(),
            "linked": attr.string_list(),
        },
        config_settings = {"//command_line_option:apple_generate_dsym": True},
        attr_values = _MACOS_HOST | {"extracted": extracted, "linked": linked},
    )

def _dsyms_are_linked_or_extracted(env, target):
    extracted = env.ctx.attr.extracted
    linked = env.ctx.attr.linked
    prefix = target.label.name + "_symbols/"
    env.expect.that_collection(
        [
            action.outputs.to_list()[0].short_path.split(prefix, 1)[1]
            for action in target[TestingAspectInfo].actions
            if action.mnemonic == "GodotDsym"
        ],
        expr = "extracted .dSYMs",
    ).contains_exactly(extracted)
    sources = {
        _tagless(entry["destination"]): entry["source"]
        for entry in _debug_symbol_entries(env, target)
    }
    env.expect.that_collection(sources.keys(), expr = "debug symbol paths").contains_exactly(
        extracted + linked,
    )
    for destination in linked:
        source = sources.get(destination, "")
        env.expect.where(destination = destination, source = source).that_bool(
            source.endswith(".dSYM") and prefix not in source,
            expr = "is the .dSYM the linker wrote",
        ).equals(True)

def _test_linked_runtime_and_extension_dsyms_are_the_linkers(name):
    _dsyms_test(
        name,
        _DSYMS + "linked_app",
        extracted = [],
        linked = [
            "Contents/MacOS/Game.dSYM",
            "Contents/Resources/native/bin/{tags}/libdsym_extension.so.dSYM",
        ],
    )

def _test_prebuilt_runtime_dsym_is_extracted(name):
    _dsyms_test(
        name,
        _DSYMS + "prebuilt_runtime_app",
        extracted = ["Contents/MacOS/Game.dSYM"],
        linked = ["Contents/Resources/native/bin/{tags}/libdsym_extension.so.dSYM"],
    )

def desktop_package_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_newer_runtime_than_editor_analyzes,
            _test_older_runtime_than_editor_analyzes,
            _test_debug_runtime_variant_analyzes,
            _test_runtime_without_runtime_info_fails,
            _test_runtime_source_file_fails,
            _test_runtime_of_other_operating_system_fails,
            _test_runtime_without_executable_fails,
            _test_liquid_glass_icon_naming_a_file_fails,
            _test_linux_packaging_reads_runtime_files,
            _test_macos_packaging_reads_runtime_and_shell_files,
            _test_host_test_and_macos_app_share_validations,
            _test_fastbuild_strips_native_code,
            _test_opt_keeps_native_code_unstripped,
            _test_strip_always_strips_native_code_in_opt,
            _test_strip_never_keeps_native_code_unstripped,
            _test_linked_runtime_and_extension_dsyms_are_the_linkers,
            _test_prebuilt_runtime_dsym_is_extracted,
        ],
    )
