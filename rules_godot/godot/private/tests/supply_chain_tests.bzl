"""Repositories of the ruleset give their targets the package metadata of the software they hold."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:supply_chain.bzl", "integrity_checksum", "source_purl", "write_package_metadata")
load(":mocks.bzl", "mocks")

visibility("private")

_SHA256 = "e954996374cbd1cb5d72e0e3781cc537408e6ce73b010b12c6c2f308a820690a"

def _test_integrity_becomes_a_hexadecimal_checksum(env):
    env.expect.that_str(
        integrity_checksum("sha256-6VSZY3TL0ctdcuDjeBzFN0CObOc7AQsSxsLzCKggaQo="),
    ).equals("sha256:" + _SHA256)

def _test_the_digest_qualifies_the_package_url(env):
    env.expect.that_str(source_purl("godot", "4.7.2", "sha256:" + _SHA256)).equals(
        "pkg:generic/godot@4.7.2?checksum=sha256:" + _SHA256,
    )
    env.expect.that_str(source_purl("godot", "4.7.2")).equals("pkg:generic/godot@4.7.2")

def _files(ctx):
    return {call.path: call.content for call in mocks.calls(ctx, "file")}

def _test_every_target_carries_the_metadata_and_license_text(env):
    ctx = mocks.repository_ctx(files = {"/tree/LICENSE.txt": "Copyright (c) Godot Engine contributors."})
    write_package_metadata(ctx, "pkg:generic/godot@4.7.2", "/tree/LICENSE.txt")
    files = _files(ctx)
    env.expect.that_str(files["REPO.bazel"]).equals(
        'repo(default_package_metadata = ["//_package_metadata:package_metadata"])\n',
    )
    env.expect.that_str(files["_package_metadata/LICENSE.txt"]).equals(
        "Copyright (c) Godot Engine contributors.",
    )
    build = files["_package_metadata/BUILD.bazel"]
    env.expect.that_str(build).contains('purl = "pkg:generic/godot@4.7.2",')
    env.expect.that_str(build).contains("licenses/spdx:MIT")
    env.expect.that_str(build).contains('text = "LICENSE.txt",')

def _test_metadata_without_license_text(env):
    ctx = mocks.repository_ctx()
    write_package_metadata(ctx, "pkg:generic/godot@4.7.2")
    files = _files(ctx)
    env.expect.that_collection(files.keys()).contains_exactly(["REPO.bazel", "_package_metadata/BUILD.bazel"])
    env.expect.that_bool("text =" in files["_package_metadata/BUILD.bazel"]).equals(False)

def supply_chain_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_integrity_becomes_a_hexadecimal_checksum,
            _test_the_digest_qualifies_the_package_url,
            _test_every_target_carries_the_metadata_and_license_text,
            _test_metadata_without_license_text,
        ],
    )
