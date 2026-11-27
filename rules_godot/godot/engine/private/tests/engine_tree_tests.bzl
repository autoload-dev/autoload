"""godot_engine_tree extracts, patches and prepares one engine's sources for all its recipes."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")

# buildifier: disable=bzl-visibility
load("//godot/engine/private:tree_repository.bzl", "engine_tree_impl")

# buildifier: disable=bzl-visibility
load("//godot/private/tests:mocks.bzl", "mocks")

_SOURCE = Label("//godot/engine/private/tests:source.json")
_SHA256 = "e954996374cbd1cb5d72e0e3781cc537408e6ce73b010b12c6c2f308a820690a"
_PYTHON = "/usr/bin/python3"
_PATCH = "/usr/bin/patch"

def _tree(*, execute = {}, **overrides):
    ctx = mocks.repository_ctx(
        attr = {
            "name": "godot_tree",
            "source": _SOURCE,
            "patches": [],
            "patch_strip": 1,
            "_python": _PYTHON,
            "_tree": "tools/engine/tree.py",
        } | overrides,
        files = {str(_SOURCE): json.encode({
            "archive": "source.tar.gz",
            "sha256": _SHA256,
            "strip_prefix": "godot-4.7.2-stable",
            "version": "4.7.2",
            "origin": "sha256:%s 4.7.2" % _SHA256,
        })},
        which = {"patch": _PATCH},
        execute = execute,
    )
    errors, fail_ = mocks.errors()
    metadata = engine_tree_impl(ctx, _fail = fail_)
    return ctx, errors, metadata

def _files(ctx):
    return {call.path: call.content for call in mocks.calls(ctx, "file")}

def _test_the_tree_is_extracted_patched_and_prepared_once(env):
    ctx, errors, metadata = _tree(patches = ["fork.patch"], patch_strip = 2)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([call.method for call in ctx.calls]).contains_exactly([
        "watch",
        "extract",
        "getenv",
        "watch",
        "execute",
        "download_and_extract",
        "execute",
        "file",
        "file",
    ]).in_order()
    extract = mocks.calls(ctx, "extract")[0]
    env.expect.that_str(extract.archive).equals(str(_SOURCE.same_package_label("source.tar.gz")))
    env.expect.that_str(extract.stripPrefix).equals("godot-4.7.2-stable")
    executions = mocks.calls(ctx, "execute")
    env.expect.that_collection(executions[0].args).contains_exactly(
        [_PATCH, "-p2", "-F0", "-t", "-N", "-i", "fork.patch"],
    ).in_order()
    env.expect.that_str(mocks.calls(ctx, "download_and_extract")[0].output).equals("_scons")
    env.expect.that_collection(executions[1].args).contains_exactly(
        [_PYTHON, "tools/engine/tree.py", "prepare", "--root", "."],
    ).in_order()
    env.expect.that_str(_files(ctx)["BUILD.bazel"]).equals('exports_files(["tree.json"])\n')

    # The digest-pinned archive and the patches determine the tree.
    env.expect.that_bool(metadata.reproducible).equals(True)

def _test_tree_json_names_what_the_recipes_repeat(env):
    ctx, errors, _metadata = _tree(patches = ["fork.patch"], patch_strip = 2)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_dict(json.decode(_files(ctx)["tree.json"])).contains_exactly({
        # A recipe's pin extracts and patches the archive again on its execution platform.
        "archive": str(_SOURCE.same_package_label("source.tar.gz")),
        "sha256": _SHA256,
        "strip_prefix": "godot-4.7.2-stable",
        "version": "4.7.2",
        "origin": "sha256:%s 4.7.2" % _SHA256,
        "patches": ["fork.patch"],
        "patch_strip": 2,
        # A recipe's configuration runs this SCons; a new release configures it again.
        "scons": "99c0e94a42a2c1182fa6859b0be697953db07ba936ecc9817ae0d218ced20b15",
    })

def _test_rejected_patch_stops_the_tree(env):
    ctx, errors, _metadata = _tree(
        patches = ["fork.patch"],
        execute = {_PATCH: {"return_code": 1, "stdout": "1 out of 1 hunk FAILED"}},
    )
    env.expect.that_collection(errors).has_size(1)
    env.expect.that_str(errors[0]).contains("Error applying patch fork.patch")
    env.expect.that_collection(mocks.calls(ctx, "download_and_extract")).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "file")).contains_exactly([])

def _test_failed_preparation_fails(env):
    ctx, errors, _metadata = _tree(execute = {_PYTHON: {"return_code": 1, "stderr": "denied"}})
    env.expect.that_collection(errors).contains_exactly([
        "godot_tree: preparing the engine tree failed:\n\ndenied",
    ])
    env.expect.that_collection(mocks.calls(ctx, "file")).contains_exactly([])

def engine_tree_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_the_tree_is_extracted_patched_and_prepared_once,
            _test_tree_json_names_what_the_recipes_repeat,
            _test_rejected_patch_stops_the_tree,
            _test_failed_preparation_fails,
        ],
    )
