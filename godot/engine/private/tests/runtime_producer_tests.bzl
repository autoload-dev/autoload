"""
What the producers of runtime payloads report in GodotRuntimeInfo: the declared facts of a
prebuilt runtime and the facts a source-built engine binary reports from its recipe.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:providers.bzl", "GodotRuntimeInfo")
load("//godot/engine/private/tests:engines.bzl", "prebuilt_runtime")

_SOURCE_BINARY = "//godot/engine/private/tests/fixtures/source_built_runtime:godot"

def _stand_in(name):
    native.genrule(
        name = name,
        outs = [name + ".txt"],
        cmd = "touch $@",
        tags = ["manual"],
    )

# A prebuilt payload reports the facts its archive declares, places its bundle files at
# their destinations and declares no deployment target or debug symbols.
def _test_prebuilt_runtime_declares_its_facts(name):
    for part in ["binary", "data", "bundle_file"]:
        _stand_in(name + "_" + part)
    prebuilt_runtime(
        name = name + "_runtime",
        binary = name + "_binary",
        bundle_files = {name + "_bundle_file": "Contents/Resources/support.txt"},
        cpu = "arm64",
        data = [name + "_data"],
        platform = "macos",
        tags = ["manual"],
        variant = "debug",
        version = "4.7.2",
    )
    analysis_test(name = name, target = name + "_runtime", impl = _prebuilt_runtime_declares_its_facts)

def _prebuilt_runtime_declares_its_facts(env, target):
    runtime = target[GodotRuntimeInfo]
    prefix = target.label.name.removesuffix("_runtime")
    for field, value in [
        ("facts_source", "declared"),
        ("origin", str(target.label)),
        ("platform", "macos"),
        ("cpu", "arm64"),
        ("environment", ""),
        ("version", "4.7.2"),
        ("variant", "debug"),
        ("minimum_os", ""),
    ]:
        env.expect.where(field = field).that_str(getattr(runtime, field)).equals(value)
    env.expect.where(field = "executable").that_str(runtime.executable.basename).equals(prefix + "_binary.txt")
    env.expect.where(field = "bundle_files").that_dict({
        destination: file.basename
        for destination, file in runtime.bundle_files.items()
    }).contains_exactly({"Contents/Resources/support.txt": prefix + "_bundle_file.txt"})
    env.expect.where(field = "files").that_collection(
        [file.basename for file in runtime.files.to_list()],
    ).contains_exactly([prefix + "_" + part + ".txt" for part in ["binary", "bundle_file", "data"]])
    env.expect.where(field = "debug_symbols").that_bool(runtime.debug_symbols == None).equals(True)

# A source-built binary reports the facts of its recipe: the canonical version, the
# deployment target it compiles for and no bundle files. Analysis configures the engine's
# native graph but builds none of it.
def _test_source_binary_reports_source_facts(name):
    analysis_test(
        name = name,
        target = _SOURCE_BINARY,
        impl = _source_binary_reports_source_facts,
    )

def _source_binary_reports_source_facts(env, target):
    runtime = target[GodotRuntimeInfo]
    for field, value in [
        ("facts_source", "source"),
        ("origin", str(target.label)),
        ("platform", "macos"),
        ("cpu", "arm64"),
        ("environment", ""),
        ("version", "4.7.2"),
        ("variant", "release"),
        ("minimum_os", "11.0"),
    ]:
        env.expect.where(field = field).that_str(getattr(runtime, field)).equals(value)
    env.expect.where(field = "bundle_files").that_dict(runtime.bundle_files).contains_exactly({})
    env.expect.where(field = "debug_symbols").that_bool(runtime.debug_symbols == None).equals(True)

# With --apple_generate_dsym, the binary reports the .dSYM directory its link writes.
def _test_source_binary_reports_linked_dsym(name):
    analysis_test(
        name = name,
        target = _SOURCE_BINARY,
        impl = _source_binary_reports_linked_dsym,
        config_settings = {"//command_line_option:apple_generate_dsym": True},
        # rules_cc writes a .dSYM only where it links for Apple platforms.
        attr_values = {"target_compatible_with": ["@platforms//os:macos"]},
    )

def _source_binary_reports_linked_dsym(env, target):
    symbols = target[GodotRuntimeInfo].debug_symbols
    env.expect.where(field = "debug_symbols").that_str(symbols.basename if symbols else "").equals(
        "engine_binary.dSYM",
    )

def runtime_producer_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_prebuilt_runtime_declares_its_facts,
            _test_source_binary_reports_linked_dsym,
            _test_source_binary_reports_source_facts,
        ],
    )
