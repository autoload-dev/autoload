"""Repositories of the ruleset give their targets the package metadata of the software they hold."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:supply_chain.bzl", "source_purl", "write_bundled_packages", "write_metadata_package", "write_package_metadata")
load(":copyright_excerpt.bzl", "COPYRIGHT_EXCERPT")
load(":mocks.bzl", "mocks")

visibility("private")

_SHA256 = "e954996374cbd1cb5d72e0e3781cc537408e6ce73b010b12c6c2f308a820690a"

def _test_integrity_becomes_a_hexadecimal_checksum(env):
    env.expect.that_str(
        source_purl("godot", "4.7.2", integrity = "sha256-6VSZY3TL0ctdcuDjeBzFN0CObOc7AQsSxsLzCKggaQo="),
    ).equals("pkg:generic/godot@4.7.2?checksum=sha256:" + _SHA256)

def _test_the_digest_qualifies_the_package_url(env):
    env.expect.that_str(source_purl("godot", "4.7.2", sha256 = _SHA256)).equals(
        "pkg:generic/godot@4.7.2?checksum=sha256:" + _SHA256,
    )
    env.expect.that_str(source_purl("godot", "4.7.2")).equals("pkg:generic/godot@4.7.2")

def _test_an_unreadable_integrity_names_no_checksum(env):
    for integrity in ["deadbeef", "sha256-abc_def", "sha512-"]:
        env.expect.where(integrity = integrity).that_str(
            source_purl("godot", "4.7.2", integrity = integrity),
        ).equals("pkg:generic/godot@4.7.2")

def _files(ctx):
    return {call.path: call.content for call in mocks.calls(ctx, "file")}

def _test_every_target_carries_the_metadata_and_license_text(env):
    ctx = mocks.repository_ctx(
        files = {"/tree/LICENSE.txt": "Copyright (c) Godot Engine contributors."},
        tree = [],
    )
    write_package_metadata(ctx, "pkg:generic/godot@4.7.2", "/tree/LICENSE.txt")
    files = _files(ctx)
    env.expect.that_str(files["REPO.bazel"]).equals(
        'repo(default_package_metadata = ["//_package_metadata:package_metadata"])\n',
    )
    env.expect.that_str(files["_package_metadata/LICENSE"]).equals(
        "Copyright (c) Godot Engine contributors.",
    )
    build = files["_package_metadata/BUILD.bazel"]
    env.expect.that_str(build).contains('purl = "pkg:generic/godot@4.7.2",')
    env.expect.that_str(build).contains("licenses/spdx:MIT")
    env.expect.that_str(build).contains('text = "LICENSE",')

def _test_metadata_without_license_text(env):
    # A source without the license file declares the license without its text.
    for license_text in [None, "/tree/LICENSE.txt"]:
        ctx = mocks.repository_ctx(tree = [])
        write_package_metadata(ctx, "pkg:generic/godot@4.7.2", license_text)
        files = _files(ctx)
        env.expect.where(license_text = license_text).that_collection(files.keys()).contains_exactly([
            "REPO.bazel",
            "_package_metadata/BUILD.bazel",
        ])
        env.expect.where(license_text = license_text).that_bool(
            "text =" in files["_package_metadata/BUILD.bazel"],
        ).equals(False)

def _test_metadata_for_some_packages_writes_no_repo_file(env):
    ctx = mocks.repository_ctx()
    write_metadata_package(ctx, "pkg:generic/godot@4.7.2")
    env.expect.that_collection(_files(ctx).keys()).contains_exactly(["_package_metadata/BUILD.bazel"])

# Each library of Godot's COPYRIGHT.txt is a package of its own: a target that carries its
# metadata, with its part of the file as the license text; :bundled_packages gathers them.
def _test_each_bundled_library_is_a_package_of_its_own(env):
    ctx = mocks.repository_ctx(files = {"/tree/COPYRIGHT.txt": COPYRIGHT_EXCERPT}, tree = [])
    write_bundled_packages(ctx, "/tree/COPYRIGHT.txt")
    files = _files(ctx)
    env.expect.that_collection(files.keys()).contains_exactly([
        "BUILD.bazel",
        "bullet_continuous_collision_detection_and_physics_library.txt",
        "servers_audio_effects_audio_effect_pitch_shift_cpp.txt",
        "smol_v.txt",
        "zlib.txt",
    ])
    env.expect.that_str(files["zlib.txt"]).contains("Copyright: 1995-2026, Jean-loup Gailly and Mark Adler")
    build = files["BUILD.bazel"]
    for text in [
        'srcs = [":bullet_continuous_collision_detection_and_physics_library", ":servers_audio_effects_audio_effect_pitch_shift_cpp", ":smol_v", ":zlib"],',
        'package_metadata = [":zlib.metadata"],',
        'purl = "pkg:generic/godot/zlib",',
        'purl = "pkg:generic/godot/SMOL-V",',
        'purl = "pkg:generic/godot/Bullet%20Continuous%20Collision%20Detection%20and%20Physics%20Library",',
        "licenses/spdx:Zlib",
        'identifier = "Unlicense OR MIT",',
        'identifier = "LicenseRef-Expat-and-WOL",',
        'text = "zlib.txt",',
    ]:
        env.expect.that_str(build).contains(text)

def _test_without_copyright_no_package_is_bundled(env):
    ctx = mocks.repository_ctx(tree = [])
    write_bundled_packages(ctx, "/tree/COPYRIGHT.txt")
    env.expect.that_collection(_files(ctx).keys()).contains_exactly(["BUILD.bazel"])
    env.expect.that_str(_files(ctx)["BUILD.bazel"]).contains('name = "bundled_packages",\n    srcs = [],')

# The metadata package names the libraries of the software's Godot from their repository.
def _test_the_metadata_package_names_the_bundled_packages(env):
    for bundled, srcs in [
        ("@@godot_bundled_packages//:bundled_packages", '["@@godot_bundled_packages//:bundled_packages"]'),
        (None, "[]"),
    ]:
        ctx = mocks.repository_ctx(tree = [])
        write_package_metadata(ctx, "pkg:generic/godot@4.7.2", bundled_packages = bundled)
        env.expect.where(bundled = bundled).that_str(_files(ctx)["_package_metadata/BUILD.bazel"]).contains(
            'name = "bundled_packages",\n    srcs = %s,' % srcs,
        )

def supply_chain_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_integrity_becomes_a_hexadecimal_checksum,
            _test_the_digest_qualifies_the_package_url,
            _test_an_unreadable_integrity_names_no_checksum,
            _test_every_target_carries_the_metadata_and_license_text,
            _test_metadata_without_license_text,
            _test_metadata_for_some_packages_writes_no_repo_file,
            _test_each_bundled_library_is_a_package_of_its_own,
            _test_without_copyright_no_package_is_bundled,
            _test_the_metadata_package_names_the_bundled_packages,
        ],
    )
