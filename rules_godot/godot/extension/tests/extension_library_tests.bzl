"""
What a godot_extension_library hands a godot_extension, and what the extension checks.

The library passes its entry symbol on, so an extension of it needs none of its own. The
extension fails when its entry_symbol differs from the library's, or when its library
carries none and it names none. The library's file is named after library_name.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("//godot/extension:defs.bzl", "godot_extension", "godot_extension_library")
load("//godot/private:providers.bzl", "GodotExtensionInfo")
load(":descriptor_tests.bzl", "descriptor_contents")

visibility("private")

_SMALL = {"size": "small"}

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

def extension_library_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_library_passes_its_entry_symbol_on,
            _test_library_is_named_after_library_name,
            _test_entry_symbol_mismatches_fail,
        ],
    )
