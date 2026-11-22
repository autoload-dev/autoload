"""godot_engine_source downloads one archive and describes it; it never extracts or configures."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")

# buildifier: disable=bzl-visibility
load("//godot/engine/private:source_repositories.bzl", "engine_source_impl")

# buildifier: disable=bzl-visibility
load("//godot/private/tests:mocks.bzl", "mocks")

_SHA256 = "e954996374cbd1cb5d72e0e3781cc537408e6ce73b010b12c6c2f308a820690a"

def _source(**overrides):
    ctx = mocks.repository_ctx(attr = {
        "name": "godot_sources",
        "urls": ["https://example.com/godot-4.7.2-stable.tar.gz"],
        "sha256": _SHA256,
        "strip_prefix": "godot-4.7.2-stable",
        "version": "4.7.2",
    } | overrides)
    errors, fail_ = mocks.errors()
    engine_source_impl(ctx, _fail = fail_)
    return ctx, errors

def _files(ctx):
    return {call.path: call.content for call in mocks.calls(ctx, "file")}

def _test_source_json_describes_the_archive(env):
    ctx, errors = _source(urls = [
        "https://example.com/godot-4.7.2-stable.tar.gz",
        "https://mirror.example.com/godot-4.7.2-stable.tar.gz",
    ])
    env.expect.that_collection(errors).contains_exactly([])
    downloads = mocks.calls(ctx, "download")
    env.expect.that_collection(downloads).has_size(1)
    env.expect.that_collection(downloads[0].url).contains_exactly([
        "https://example.com/godot-4.7.2-stable.tar.gz",
        "https://mirror.example.com/godot-4.7.2-stable.tar.gz",
    ]).in_order()
    env.expect.that_str(downloads[0].output).equals("source.tar.gz")
    env.expect.that_str(downloads[0].sha256).equals(_SHA256)
    files = _files(ctx)
    env.expect.that_dict(json.decode(files["source.json"])).contains_exactly({
        "archive": "source.tar.gz",
        "sha256": _SHA256,
        "strip_prefix": "godot-4.7.2-stable",
        "version": "4.7.2",
        "origin": "sha256:%s 4.7.2" % _SHA256,
    })
    env.expect.that_str(files["BUILD.bazel"]).equals('exports_files(["source.json", "source.tar.gz"])\n')
    env.expect.that_collection(mocks.calls(ctx, "extract")).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "download_and_extract")).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "execute")).contains_exactly([])

def _test_archive_type_follows_the_first_url(env):
    ctx, errors = _source(urls = [
        "https://example.com/godot.zip?token=1",
        "https://mirror.example.com/godot.tar.gz",
    ])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(mocks.calls(ctx, "download")[0].output).equals("source.zip")
    env.expect.that_str(json.decode(_files(ctx)["source.json"])["archive"]).equals("source.zip")

def _test_unknown_archive_type_fails(env):
    ctx, errors = _source(urls = ["https://example.com/godot.7z"])
    env.expect.that_collection(errors).contains_exactly([
        "godot_engine_source cannot tell the archive type of https://example.com/godot.7z; " +
        "supported: .tar.gz, .tgz, .tar.xz, .tar.bz2, .tar.zst, .zip",
    ])
    env.expect.that_collection(ctx.calls).contains_exactly([])

def _test_empty_urls_fail(env):
    ctx, errors = _source(urls = [])
    env.expect.that_collection(errors).contains_exactly([
        "godot_sources: urls must list at least one mirror of the archive",
    ])
    env.expect.that_collection(ctx.calls).contains_exactly([])

def _test_unsupported_source_version_fails(env):
    ctx, errors = _source(version = "4.7.2-beta")
    env.expect.that_collection(errors).contains_exactly([
        "Source prerelease is older than the supported stable floor: 4.7.2-beta",
    ])
    env.expect.that_collection(ctx.calls).contains_exactly([])

def engine_source_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_source_json_describes_the_archive,
            _test_archive_type_follows_the_first_url,
            _test_unknown_archive_type_fails,
            _test_empty_urls_fail,
            _test_unsupported_source_version_fails,
        ],
    )
