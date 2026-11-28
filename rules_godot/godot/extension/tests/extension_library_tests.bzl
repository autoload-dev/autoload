"""
What a godot_extension_library hands a godot_extension, and what the extension checks.

The library passes its entry symbol on, so an extension of it needs none of its own. The
extension fails when its entry_symbol differs from the library's, or when its library
carries none and it names none. The library's file is named after library_name. On iOS the
extension carries the dynamic frameworks the library's code links, so applications embed them.
An engine whose Godot minor has no pinned Emscripten release gets a web toolchain that says so.
"""

load("@rules_apple//apple:providers.bzl", "AppleFrameworkImportInfo")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("//godot/extension:defs.bzl", "godot_extension", "godot_extension_library")
load("//godot/extension/private/emscripten:unpinned.bzl", "emscripten_unpinned_toolchain")
load("//godot/private:providers.bzl", "GodotExtensionInfo")
load("//godot/private/tests:fixture_files.bzl", "fixture_file")
load(":descriptor_tests.bzl", "descriptor_contents")
load(":library_fixtures.bzl", "dynamic_xcframework_fixture")

visibility("private")

_SMALL = {"size": "small"}
_IOS_SIMULATOR = {"//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_arm64"))}

def _library(name, **kwargs):
    godot_extension_library(
        name = name,
        deps = [":runtime_only_dependency"],
        entry_symbol = "archive_fixture_init",
        tags = ["manual"],
        **kwargs
    )

def _test_library_passes_its_entry_symbol_on(name):
    _library(name + "_library")
    godot_extension(name = name + "_extension", library = ":" + name + "_library", tags = ["manual"])
    analysis_test(
        name = name,
        target = name + "_extension",
        impl = _library_passes_its_entry_symbol_on,
        attr_values = _SMALL,
    )

def _library_passes_its_entry_symbol_on(env, target):
    env.expect.that_str(target[GodotExtensionInfo].entry_symbol).equals("archive_fixture_init")
    for content in descriptor_contents(target):
        env.expect.that_collection(content.split("\n")).contains('entry_symbol = "archive_fixture_init"')

def _test_library_is_named_after_library_name(name):
    _library(name + "_library", library_name = "game")
    godot_extension(name = name + "_extension", library = ":" + name + "_library", tags = ["manual"])
    analysis_test(
        name = name,
        target = name + "_extension",
        impl = _library_is_named_after_library_name,
        attr_values = _SMALL,
    )

def _library_is_named_after_library_name(env, target):
    env.expect.that_str(target[GodotExtensionInfo].library.file.basename).equals("libgame.so")

def _test_entry_symbol_mismatches_fail(name):
    _library(name + "_library")
    godot_extension(
        name = name + "_different",
        entry_symbol = "other_init",
        library = ":" + name + "_library",
        tags = ["manual"],
    )
    godot_extension(name = name + "_unnamed", library = ":android_fixture", tags = ["manual"])
    analysis_test(
        name = name,
        targets = {"different": name + "_different", "unnamed": name + "_unnamed"},
        impl = _entry_symbol_mismatches_fail,
        attr_values = _SMALL,
        expect_failure = True,
    )

def _entry_symbol_mismatches_fail(env, targets):
    env.expect.that_target(targets.different).failures().contains_predicate(
        matching.contains("entry symbol other_init differs from archive_fixture_init"),
    )
    env.expect.that_target(targets.unnamed).failures().contains_predicate(
        matching.contains("carries no entry symbol; name it with entry_symbol"),
    )

def _test_ios_extension_carries_the_frameworks_the_code_links(name):
    dynamic_xcframework_fixture(name = name + "_core", binary = "FixtureCore", linked = True)
    cc_library(name = name + "_code", srcs = ["static_fixture.cc"], deps = [":" + name + "_core"], tags = ["manual"])
    godot_extension_library(
        name = name + "_library",
        deps = [":" + name + "_code"],
        entry_symbol = "archive_fixture_init",
        tags = ["manual"],
    )
    godot_extension(name = name + "_extension", library = ":" + name + "_library", tags = ["manual"])
    analysis_test(
        name = name,
        target = name + "_extension",
        impl = _ios_extension_carries_the_frameworks_the_code_links,
        attr_values = _SMALL | {"target_compatible_with": ["@platforms//os:macos"]},
        config_settings = _IOS_SIMULATOR,
    )

def _ios_extension_carries_the_frameworks_the_code_links(env, target):
    binaries = [
        file.basename
        for file in target[AppleFrameworkImportInfo].framework_imports.to_list()
        if file.extension != "plist"
    ]
    env.expect.that_collection(binaries).contains("FixtureCore")

_WEB_THREADS = {"//command_line_option:platforms": str(Label("//godot/platforms:web_wasm32_threads"))}

def _test_prebuilt_side_module_loads_on_the_web(name):
    fixture_file(name = name + "_module", out = name + "/libprebuilt.wasm")
    godot_extension(
        name = name + "_extension",
        entry_symbol = "prebuilt_init",
        library = select({
            "//godot/platforms:is_web": ":" + name + "_module",
            "//conditions:default": None,
        }),
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = name + "_extension",
        impl = _prebuilt_side_module_loads_on_the_web,
        attr_values = _SMALL,
        config_settings = _WEB_THREADS,
    )

# A prebuilt .wasm side module is the web's dynamic library; its feature tags carry the
# threads ABI, as Godot's own web libraries do.
def _prebuilt_side_module_loads_on_the_web(env, target):
    library = target[GodotExtensionInfo].library
    env.expect.that_str(library.link_kind).equals("dynamic")
    env.expect.that_str(library.tags).equals("web.wasm32.threads.release")
    env.expect.that_str(library.file.basename).equals("libprebuilt.wasm")

def _test_an_engine_without_an_emscripten_release_says_so(name):
    emscripten_unpinned_toolchain(
        name = name + "_toolchain",
        engine = "future",
        series = "4.9",
        version = "4.9.0-stable",
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = name + "_toolchain",
        impl = _an_engine_without_an_emscripten_release_says_so,
        attr_values = _SMALL,
        expect_failure = True,
    )

def _an_engine_without_an_emscripten_release_says_so(env, target):
    env.expect.that_target(target).failures().contains_predicate(matching.contains(
        "The engine future has no web toolchain: rules_godot pins no Emscripten release for Godot 4.9 (4.9.0-stable)",
    ))

def extension_library_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_library_passes_its_entry_symbol_on,
            _test_library_is_named_after_library_name,
            _test_entry_symbol_mismatches_fail,
            _test_ios_extension_carries_the_frameworks_the_code_links,
            _test_prebuilt_side_module_loads_on_the_web,
            _test_an_engine_without_an_emscripten_release_says_so,
        ],
    )
