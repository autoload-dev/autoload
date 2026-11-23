"""
Which form of a pack --@autoload_rules_godot//godot:pack_conversion and the compilation mode build.

The written form runs Godot only on the pack's configuration, so an edit of the pack's
content reruns the writer and no Godot action that exports.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load(
    ":action_inputs.bzl",
    "build_graph",
    "expect_built_not_read",
    "expect_built_reads",
    "godot_actions",
    "mnemonics_of",
)
load(":pack_forms.bzl", "PACK_CONVERSION")

_PACK = "//godot/private/tests/fixtures/project_with_imported_assets:pack"
_COMPILATION_MODE = "//command_line_option:compilation_mode"

# Besides the pack, the validations of the units whose closure holds a file stage it, the
# class fragment of its unit reads a script, and the pack's reference check scans every
# member.
_CONTENT_CHECKS = ["GodotClassFragment", "GodotResourceGraph", "GodotValidate"]

def _analysis_test(name, impl, settings = {}, expect_failure = False):
    analysis_test(
        name = name,
        target = _PACK,
        impl = impl,
        config_settings = settings,
        expect_failure = expect_failure,
        extra_target_under_test_aspects = [godot_actions],
    )

def _expect_form(env, target, present, absent):
    mnemonics = mnemonics_of(target)
    for mnemonic in present:
        env.expect.that_collection(mnemonics).contains(mnemonic)
    for mnemonic in absent:
        env.expect.that_collection(mnemonics).not_contains(mnemonic)

def _expect_written(env, target):
    _expect_form(env, target, ["GodotPackConfiguration", "GodotPackWrite"], ["GodotPack"])

def _expect_exported(env, target):
    _expect_form(env, target, ["GodotPack"], ["GodotPackConfiguration", "GodotPackWrite"])

def _test_auto_writes_outside_optimized_builds(name):
    _analysis_test(name, _expect_written, {_COMPILATION_MODE: "fastbuild"})

def _test_auto_writes_debug_builds(name):
    _analysis_test(name, _expect_written, {_COMPILATION_MODE: "dbg"})

def _test_auto_exports_optimized_builds(name):
    _analysis_test(name, _expect_exported, {_COMPILATION_MODE: "opt"})

def _test_godot_exports_any_build(name):
    _analysis_test(name, _expect_exported, {PACK_CONVERSION: "godot", _COMPILATION_MODE: "fastbuild"})

def _test_none_rejects_optimized_builds(name):
    _analysis_test(
        name,
        _fails_for_optimized_builds,
        {PACK_CONVERSION: "none", _COMPILATION_MODE: "opt"},
        expect_failure = True,
    )

def _fails_for_optimized_builds(env, target):
    env.expect.that_target(target).failures().contains_predicate(
        matching.str_matches("*pack_conversion=none*development builds only*"),
    )

# A script edit reruns the writer, and neither the configuration export nor any other
# export.
def _test_script_reaches_only_the_writer(name):
    _analysis_test(name, _script_reaches_only_the_writer)

def _script_reaches_only_the_writer(env, target):
    graph = build_graph(target)
    expect_built_reads(env, graph, "GodotPackWrite", "main/main.gd")
    expect_built_not_read(env, graph, "main/main.gd", readers = ["GodotPackWrite"] + _CONTENT_CHECKS)

# An imported asset's new import result reruns the writer, not the configuration export.
def _test_import_result_reaches_the_writer_not_the_configuration(name):
    _analysis_test(name, _import_result_reaches_the_writer_not_the_configuration)

def _import_result_reaches_the_writer_not_the_configuration(env, target):
    graph = build_graph(target)
    icon = "godot/private/tests/fixtures/project_with_imported_assets/icon.import"
    expect_built_reads(env, graph, "GodotPackWrite", icon)
    expect_built_not_read(env, graph, "project_with_imported_assets/icon.import", readers = ["GodotMetadataIndex", "GodotPackWrite"])

def pack_conversion_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_auto_exports_optimized_builds,
            _test_auto_writes_debug_builds,
            _test_auto_writes_outside_optimized_builds,
            _test_godot_exports_any_build,
            _test_import_result_reaches_the_writer_not_the_configuration,
            _test_none_rejects_optimized_builds,
            _test_script_reaches_only_the_writer,
        ],
    )
