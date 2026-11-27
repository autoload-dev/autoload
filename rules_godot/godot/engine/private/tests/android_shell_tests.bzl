"""godot_android_shell prepares Godot's Android shell library from its engine tree."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private:source_repositories.bzl", "android_shell_impl")
load("//godot/private/tests:mocks.bzl", "mocks")

visibility("private")

_TREE = Label("//godot/engine/private/tests:tree.json")
_MANIFEST_PATH = "platform/android/java/lib/src/main/AndroidManifest.xml"
_MANIFEST = """<manifest android:versionName="${godotLibraryVersion}">

    <application>
    </application>
</manifest>
"""
_PYTHON = "/usr/bin/python3"

# Godot's license text in the engine tree, beside its descriptor.
_LICENSE = mocks.path(_TREE).dirname + "/LICENSE.txt"

def _shell(*, version = "4.7.2", manifest = _MANIFEST, execute = {}, **overrides):
    ctx = mocks.repository_ctx(
        attr = {
            "name": "godot_android_shell",
            "tree": _TREE,
            "patches": ["@@//engines:java.patch"],
            "patch_strip": 1,
            "_build_template": "android_shell.BUILD.tpl",
            "_kotlin_android": "@@rules_kotlin+//kotlin:android.bzl",
            "_kotlin_core": "@@rules_kotlin+//kotlin:core.bzl",
            "_python": _PYTHON,
            "_tree": "rules_godot/tools/engine/tree.py",
            "_tree_link": "rules_godot/tools/engine/tree_link.py",
            "_class_db": "rules_godot/tools/engine/class_db.py",
            "_patches": "rules_godot/tools/engine/patches.py",
        } | overrides,
        files = {
            str(_TREE): json.encode({
                "archive": "@@godot_sources//:source.tar.gz",
                "sha256": "0" * 64,
                "strip_prefix": "godot-%s" % version,
                "version": version,
            }),
            _MANIFEST_PATH: manifest,
            _LICENSE: "Copyright (c) Godot Engine contributors.",
        },
        execute = execute,
        path = lambda value: mocks.path(value) if str(value) in (str(_TREE), _LICENSE) else str(value),
    )
    errors, fail_ = mocks.errors()
    android_shell_impl(ctx, _fail = fail_)
    return ctx, errors

def _files(ctx):
    return {call.path: call.content for call in mocks.calls(ctx, "file")}

# The shell links the library's files of its engine tree, patches its own copies of the
# files the engine's patches touch, and extracts nothing itself.
def _test_shell_links_the_library_of_its_engine_tree(env):
    ctx, errors = _shell()
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "extract")).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "execute")[0].args).contains_exactly([
        _PYTHON,
        "-P",
        "-m",
        "tools.engine.tree_link",
        "--tree",
        str(_TREE).rpartition("/")[0],
        "--recipe",
        ".",
        "--path",
        "platform/android/java/lib",
        "--patch-strip",
        "1",
        "--patch",
        "@@//engines:java.patch",
    ]).in_order()

    env.expect.that_collection([call.path for call in mocks.calls(ctx, "watch")]).contains(
        "rules_godot/tools/engine/tree_link.py",
    )

def _test_a_failed_link_stops_the_shell(env):
    ctx, errors = _shell(execute = {_PYTHON: {"return_code": 1, "stderr": "denied"}})
    env.expect.that_collection(errors).contains_exactly([
        "godot_android_shell: linking the engine tree failed:\n\ndenied",
    ])
    env.expect.that_collection(mocks.calls(ctx, "file")).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def _test_each_variant_gets_a_build_config(env):
    ctx, errors = _shell()
    env.expect.that_collection(errors).contains_exactly([])
    files = _files(ctx)
    env.expect.that_str(files["_build_config/debug/org/godotengine/godot/BuildConfig.java"]).equals("""package org.godotengine.godot;

public final class BuildConfig {
  public static final boolean DEBUG = true;
  public static final String LIBRARY_PACKAGE_NAME = "org.godotengine.godot";
  public static final String BUILD_TYPE = "debug";
  public static final String FLAVOR = "template";
}
""")
    release = files["_build_config/release/org/godotengine/godot/BuildConfig.java"]
    env.expect.that_str(release).contains("DEBUG = false;")
    env.expect.that_str(release).contains('BUILD_TYPE = "release";')
    templates = mocks.calls(ctx, "template")
    env.expect.that_collection(templates).has_size(1)
    env.expect.that_str(templates[0].path).equals("BUILD.bazel")
    env.expect.that_str(templates[0].template).equals("android_shell.BUILD.tpl")
    env.expect.that_dict(templates[0].substitutions).contains_exactly({
        "{KOTLIN_ANDROID}": repr("@@rules_kotlin+//kotlin:android.bzl"),
        "{KOTLIN_CORE}": repr("@@rules_kotlin+//kotlin:core.bzl"),
        "{LIBRARY}": repr("platform/android/java/lib"),
        "{PACKAGE}": repr("org.godotengine.godot"),
        "{PACKAGE_PATH}": repr("org/godotengine/godot"),
        "{JAVA_LEVEL}": repr("17"),
        "{DEPS}": repr([str(Label(dep)) for dep in [
            "@maven//:androidx_annotation_annotation_jvm",
            "@maven//:androidx_documentfile_documentfile",
            "@maven//:androidx_fragment_fragment",
            "@maven//:org_jetbrains_annotations",
            "@maven//:org_jetbrains_kotlin_kotlin_stdlib",
        ]]),
    })

def _test_manifest_gets_version_and_min_sdk(env):
    for version, name in [("4.7.2", "4.7.2.stable"), ("4.8.0-beta1", "4.8.0.beta1")]:
        ctx, errors = _shell(version = version)
        env.expect.where(version = version).that_collection(errors).contains_exactly([])
        env.expect.where(version = version).that_str(_files(ctx)["AndroidManifest.xml"]).equals(
            """<manifest android:versionName="%s">

    <uses-sdk android:minSdkVersion="24" />

    <application>
    </application>
</manifest>
""" % name,
        )

def _test_manifest_without_placeholder_fails(env):
    for manifest in [
        _MANIFEST.replace("${godotLibraryVersion}", "4.7.2"),
        _MANIFEST.replace("<application>", "<application android:label=\"x\">"),
    ]:
        ctx, errors = _shell(manifest = manifest)
        env.expect.where(manifest = manifest).that_collection(errors).contains_exactly([
            "godot_android_shell: the Android shell manifest of Godot 4.7.2 lacks the expected placeholder",
        ])
        env.expect.where(manifest = manifest).that_collection(mocks.calls(ctx, "file")).contains_exactly([])
        env.expect.where(manifest = manifest).that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def android_shell_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_shell_links_the_library_of_its_engine_tree,
            _test_a_failed_link_stops_the_shell,
            _test_each_variant_gets_a_build_config,
            _test_manifest_gets_version_and_min_sdk,
            _test_manifest_without_placeholder_fails,
        ],
    )
