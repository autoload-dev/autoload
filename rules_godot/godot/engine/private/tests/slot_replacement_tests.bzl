"""A registration set ahead of the prebuilt hub replaces only its own slots.

The release-slot set of fixtures/release_override replaces the desktop release runtime; the
debug slot is not in that set, so the prebuilt hub keeps it.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private/tests:engines.bzl", "ResolvedInfo", "resolution_probe")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

_RELEASE_OVERRIDE = "//godot/engine/private/tests/fixtures/release_override"

def _desktop_probe(name):
    # The fixture covers the desktop slots of the host platform; an incompatible probe makes
    # the test incompatible too.
    resolution_probe(
        name = name,
        tags = ["manual"],
        target_compatible_with = select({
            "@platforms//os:linux": [],
            "@platforms//os:macos": [],
            "//conditions:default": ["@platforms//:incompatible"],
        }),
    )
    return name

def _settings(variant):
    # Toolchains registered through the command line precede the MODULE.bazel registration
    # of @godot; that priority is the subject.
    return {
        str(Label("//godot:variant")): variant,
    } | own_toolchains([_RELEASE_OVERRIDE + ":all"])

def _runtime_provenance(env, target):
    runtime = target[ResolvedInfo].runtime
    env.expect.that_bool(runtime != None, "the runtime must resolve").equals(True)
    return runtime.provenance if runtime else None

def _test_release_set_replaces_release_slot(name):
    analysis_test(
        name = name,
        target = _desktop_probe(name + "_probe"),
        impl = _test_release_set_replaces_release_slot_impl,
        config_settings = _settings("release"),
    )

def _test_release_set_replaces_release_slot_impl(env, target):
    provenance = _runtime_provenance(env, target)
    if provenance:
        env.expect.that_str(Label(provenance.component).package).equals(
            Label(_RELEASE_OVERRIDE + ":all").package,
        )
        env.expect.that_str(provenance.origin).equals("consumer registration set")

def _test_release_set_keeps_prebuilt_debug_slot(name):
    analysis_test(
        name = name,
        target = _desktop_probe(name + "_probe"),
        impl = _test_release_set_keeps_prebuilt_debug_slot_impl,
        config_settings = _settings("debug"),
    )

def _test_release_set_keeps_prebuilt_debug_slot_impl(env, target):
    provenance = _runtime_provenance(env, target)
    if provenance:
        # The root module registers the prebuilt hub @godot.
        env.expect.that_str(Label(provenance.component).repo_name.split("+")[-1]).equals("godot")

def slot_replacement_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_release_set_replaces_release_slot,
            _test_release_set_keeps_prebuilt_debug_slot,
        ],
    )
