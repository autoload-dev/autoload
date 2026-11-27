"""Compatibility ranges accept future releases without extending a whitelist."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")

# Exercise the private validation helper at its boundary.
load(
    "//godot/private:versions.bzl",
    "godot_minimum_error",
    "godot_version_error",
    "godot_version_name",
    "require_supported_godot_version",
    "require_supported_source_version",
    "version_below",
)
load(":mocks.bzl", "mocks")

visibility("private")

def _test_version_below_compares_numeric_parts(env):
    # Deployment targets compare by their numeric parts; a missing part is zero.
    for lower, higher in [("10.15", "11.0"), ("11.0", "11.0.1"), ("11", "11.1"), ("12.0", "13.0")]:
        env.expect.where(lower = lower, higher = higher).that_bool(version_below(lower, higher)).equals(True)
        env.expect.where(lower = higher, higher = lower).that_bool(version_below(higher, lower)).equals(False)
    for left, right in [("11.0", "11"), ("11.0", "11.0.0")]:
        env.expect.where(lower = left, higher = right).that_bool(version_below(left, right)).equals(False)

_SUPPORTED = [
    "4.7.2",
    "4.7.10",
    "4.8.0",
    "4.8.1",
    "4.9.0",
    "4.99.42",
    "4.8.0-dev1",
    "4.8.0-beta1",
    "4.8.0-rc2",
    "4.7.3-rc1",
]

def _test_godot_version_error_accepts_later_releases(env):
    env.expect.that_dict({version: godot_version_error(version) for version in _SUPPORTED}).contains_exactly(
        {version: None for version in _SUPPORTED},
    )

def _test_godot_version_error_rejects_versions_outside_the_range(env):
    for version in [
        "3.6.2",
        "4.5.1",
        "4.7.0",
        "4.7.1",
        "4.7.2-dev1",
        "4.7.2-beta1",
        "4.7.2-rc1",
        "5.0.0",
        "5.0.0-beta1",
    ]:
        env.expect.where(version = version).that_str(godot_version_error(version)).contains("requires Godot 4.7.2")

def _test_godot_version_error_rejects_malformed_versions(env):
    for version in [
        "",
        "fixture",
        "4.7",
        "4.7.2.stable",
        "4.07.2",
        "4..2",
        "4.x.2",
        "4.8-beta1",
        "4.8.0-beta0",
        "4.8.0-beta01",
        "4.8.0-alpha1",
        "4.8.0-beta1-custom",
        "4.8.0+build",
    ]:
        env.expect.where(version = version).that_str(godot_version_error(version)).contains("major.minor.patch")

def _test_godot_minimum_error_requires_a_supported_stable_release(env):
    stable = ["4.7.2", "4.8.0", "4.9.42"]
    env.expect.that_dict({version: godot_minimum_error(version) for version in stable}).contains_exactly(
        {version: None for version in stable},
    )
    for version in ["4.8.0-dev1", "4.8.0-beta1", "4.8.0-rc1"]:
        env.expect.where(version = version).that_str(godot_minimum_error(version)).contains("must be a stable")
    env.expect.that_str(godot_minimum_error("4.7.1")).contains("requires Godot 4.7.2")

def _test_godot_version_name_follows_godot_release_names(env):
    canonical_names = {
        "4.7.2": "4.7.2.stable",
        "4.8.0": "4.8.stable",
        "4.8.0-beta1": "4.8.beta1",
        "4.8.1-rc2": "4.8.1.rc2",
        "4.8.0-dev7": "4.8.dev7",
    }
    env.expect.that_dict({canonical: godot_version_name(canonical) for canonical in canonical_names}).contains_exactly(
        canonical_names,
    )

def _check(require, version):
    errors, fail_ = mocks.errors()
    supported = require(version, _fail = fail_)
    return supported, errors

def _test_supported_godot_version_passes_the_check(env):
    for version in ["4.7.2", "4.8.0-beta1"]:
        supported, errors = _check(require_supported_godot_version, version)
        env.expect.where(version = version).that_bool(supported).equals(True)
        env.expect.where(version = version).that_collection(errors).contains_exactly([])

def _test_unsupported_godot_version_fails_the_check(env):
    supported, errors = _check(require_supported_godot_version, "4.7.1")
    env.expect.that_bool(supported).equals(False)
    env.expect.that_collection(errors).contains_exactly([
        "rules_godot requires Godot 4.7.2 or newer within Godot 4 (>=4.7.2 <5.0.0); got 4.7.1",
    ])

def _test_unnumbered_source_prereleases_pass_the_check(env):
    for version in ["4.7.2", "4.8.0-dev", "4.8.0-alpha", "4.8.0-beta", "4.8.0-rc", "4.8.0-beta2"]:
        supported, errors = _check(require_supported_source_version, version)
        env.expect.where(version = version).that_bool(supported).equals(True)
        env.expect.where(version = version).that_collection(errors).contains_exactly([])

def _test_source_prerelease_of_the_floor_fails_the_check(env):
    supported, errors = _check(require_supported_source_version, "4.7.2-beta")
    env.expect.that_bool(supported).equals(False)
    env.expect.that_collection(errors).contains_exactly([
        "Source prerelease is older than the supported stable floor: 4.7.2-beta",
    ])

def _test_source_version_outside_the_range_fails_once(env):
    for version in ["4.7.1-rc", "5.0.0"]:
        supported, errors = _check(require_supported_source_version, version)
        env.expect.where(version = version).that_bool(supported).equals(False)
        env.expect.where(version = version).that_collection(errors).has_size(1)
        env.expect.where(version = version).that_str(errors[0]).contains("requires Godot 4.7.2 or newer")

def versions_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_version_below_compares_numeric_parts,
            _test_godot_version_error_accepts_later_releases,
            _test_godot_version_error_rejects_versions_outside_the_range,
            _test_godot_version_error_rejects_malformed_versions,
            _test_godot_minimum_error_requires_a_supported_stable_release,
            _test_godot_version_name_follows_godot_release_names,
            _test_supported_godot_version_passes_the_check,
            _test_unsupported_godot_version_fails_the_check,
            _test_unnumbered_source_prereleases_pass_the_check,
            _test_source_prerelease_of_the_floor_fails_the_check,
            _test_source_version_outside_the_range_fails_once,
        ],
    )
