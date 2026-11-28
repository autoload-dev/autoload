"""godot_editor_archive downloads a pinned editor archive and names its binary in the BUILD file."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private:archives.bzl", "editor_archive_impl")
load("//godot/private/tests:mocks.bzl", "mocks")

visibility("private")

_BINARY = "Godot.app/Contents/MacOS/Godot"
_INTEGRITY = "sha512-" + "A" * 86 + "=="

def _editor(*, tree = [_BINARY], **overrides):
    ctx = mocks.repository_ctx(
        attr = {
            "urls": ["https://example.com/godot-editor.zip", "https://mirror.example.com/godot-editor.zip"],
            "integrity": _INTEGRITY,
            "version": "4.7.2",
            "binary": _BINARY,
            "bundled_packages": None,
            "_prebuilt_bzl": "@@//godot/engine/private:prebuilt.bzl",
            "_build_template": "editor_archive.BUILD.tpl",
        } | overrides,
        tree = tree,
    )
    errors, fail_ = mocks.errors()
    editor_archive_impl(ctx, _fail = fail_)
    return ctx, errors

def _test_editor_build_names_the_binary(env):
    ctx, errors = _editor()
    env.expect.that_collection(errors).contains_exactly([])
    downloads = mocks.calls(ctx, "download_and_extract")
    env.expect.that_collection(downloads).has_size(1)
    env.expect.that_collection(downloads[0].url).contains_exactly([
        "https://example.com/godot-editor.zip",
        "https://mirror.example.com/godot-editor.zip",
    ]).in_order()
    env.expect.that_str(downloads[0].integrity).equals(_INTEGRITY)
    env.expect.that_str(downloads[0].type).equals("zip")
    templates = mocks.calls(ctx, "template")
    env.expect.that_collection(templates).has_size(1)
    env.expect.that_str(templates[0].path).equals("BUILD.bazel")
    env.expect.that_str(templates[0].template).equals("editor_archive.BUILD.tpl")
    env.expect.that_dict(templates[0].substitutions).contains_exactly({
        "{PREBUILT_BZL}": repr("@@//godot/engine/private:prebuilt.bzl"),
        "{BINARY}": repr(_BINARY),
        "{BUNDLED_PACKAGES}": repr("//_package_metadata:bundled_packages"),
        "{DIGEST}": repr(_INTEGRITY),
    })

def _test_unsupported_version_fails(env):
    ctx, errors = _editor(version = "4.7.1")
    env.expect.that_collection(errors).contains_exactly([
        "rules_godot requires Godot 4.7.2 or newer within Godot 4 (>=4.7.2 <5.0.0); got 4.7.1",
    ])
    env.expect.that_collection(ctx.calls).contains_exactly([])

def _test_editor_archive_without_integrity_fails(env):
    ctx, errors = _editor(integrity = "")
    env.expect.that_collection(errors).contains_exactly([
        "integrity is required: every Godot download must be checksum-pinned",
    ])
    env.expect.that_collection(ctx.calls).contains_exactly([])

def _test_binary_absent_from_archive_fails(env):
    ctx, errors = _editor(tree = ["Godot.app/Contents/Info.plist"])
    env.expect.that_collection(errors).contains_exactly([
        "Godot editor archive does not contain Godot.app/Contents/MacOS/Godot",
    ])
    env.expect.that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def editor_archive_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_editor_build_names_the_binary,
            _test_unsupported_version_fails,
            _test_editor_archive_without_integrity_fails,
            _test_binary_absent_from_archive_fails,
        ],
    )
