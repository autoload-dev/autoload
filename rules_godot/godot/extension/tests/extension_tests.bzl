"""
What a godot_extension's attributes write into its descriptor and GodotExtensionInfo, and
the values it rejects.

A compatibility minimum and reloadable reach the descriptor as written; the entry symbol and minimum operating-system versions reach GodotExtensionInfo; a
minimum Godot does not support and a minimum operating-system version that is not dotted
fail analysis.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("//godot/extension:defs.bzl", "godot_extension")
load("//godot/private:providers.bzl", "GodotExtensionInfo")
load(":descriptor_tests.bzl", "descriptor_contents")

visibility("private")

_SMALL = {"size": "small"}

def _extension(name, **kwargs):
    godot_extension(
        name = name,
        entry_symbol = "extension_fixture_init",
        library = ":android_fixture",
        tags = ["manual"],
        **kwargs
    )

def _descriptor_test(name, lines, **kwargs):
    _extension(name + "_extension", **kwargs)
    analysis_test(
        name = name,
        target = name + "_extension",
        impl = _descriptor_holds_lines,
        attrs = {"lines": attr.string_list()},
        attr_values = _SMALL | {"lines": lines},
    )

def _descriptor_holds_lines(env, target):
    contents = descriptor_contents(target)
    env.expect.that_collection(contents, expr = "descriptor contents").has_size(1)
    for content in contents:
        env.expect.that_collection(content.split("\n"), expr = "descriptor lines").contains_at_least(
            env.ctx.attr.lines,
        )

def _failure_test(name, cases):
    """Declare one extension per (attributes, message) case and expect each to fail with its message."""
    targets = {}
    for index, (attributes, _) in enumerate(cases):
        _extension("%s_extension_%d" % (name, index), **attributes)
        targets["case_%d" % index] = "%s_extension_%d" % (name, index)
    analysis_test(
        name = name,
        targets = targets,
        impl = _fails_with_messages,
        attrs = {"messages": attr.string_list()},
        attr_values = _SMALL | {"messages": [message for _, message in cases]},
        expect_failure = True,
    )

def _fails_with_messages(env, targets):
    for index, message in enumerate(env.ctx.attr.messages):
        env.expect.that_target(getattr(targets, "case_%d" % index)).failures().contains_predicate(
            matching.contains(message),
        )

def _test_compatibility_minimum_reaches_descriptor(name):
    _descriptor_test(
        name,
        ['compatibility_minimum = "4.8.0"'],
        compatibility_minimum = "4.8.0",
    )

def _test_unsupported_compatibility_minimum_fails(name):
    _failure_test(name, [
        ({"compatibility_minimum": "4.6.0"}, "rules_godot requires Godot 4.7.2 or newer within Godot 4"),
        (
            {"compatibility_minimum": "4.8.0-beta1"},
            "GDExtension compatibility_minimum must be a stable major.minor.patch version; got \"4.8.0-beta1\"",
        ),
    ])

def _test_reloadable_reaches_descriptor(name):
    _descriptor_test(name, ["reloadable = true"], reloadable = True)

def _test_non_dotted_minimum_os_version_fails(name):
    _failure_test(name, [(
        {"minimum_os_versions": {"macos": "13.x"}},
        "minimum_os_versions[macos] must be a dotted numeric version; got \"13.x\"",
    )])

def _test_extension_info_carries_entry_symbol_and_minimum_os_versions(name):
    _extension(name + "_extension", minimum_os_versions = {"macos": "11.0"})
    analysis_test(
        name = name,
        target = name + "_extension",
        impl = _extension_info_carries_entry_symbol_and_minimum_os_versions,
        attr_values = _SMALL,
    )

def _extension_info_carries_entry_symbol_and_minimum_os_versions(env, target):
    extension = target[GodotExtensionInfo]
    env.expect.where(field = "entry_symbol").that_str(extension.entry_symbol).equals("extension_fixture_init")
    env.expect.where(field = "minimum_os_versions").that_dict(extension.minimum_os_versions).contains_exactly({
        "macos": "11.0",
    })

def extension_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_extension_info_carries_entry_symbol_and_minimum_os_versions,
            _test_compatibility_minimum_reaches_descriptor,
            _test_unsupported_compatibility_minimum_fails,
            _test_reloadable_reaches_descriptor,
            _test_non_dotted_minimum_os_version_fails,
        ],
    )
