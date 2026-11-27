"""Source patches apply strictly with the patch tool, and a rejected patch stops the repository."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:patches.bzl", "apply_repository_patches")
load(":mocks.bzl", "mocks")

visibility("private")

_PATCH = "/usr/bin/patch"

def _apply(patches, *, which = {"patch": _PATCH}, execute = {}, patch_strip = 1):
    ctx = mocks.repository_ctx(
        attr = {"patches": patches, "patch_strip": patch_strip},
        which = which,
        execute = execute,
    )
    errors, fail_ = mocks.errors()
    applied = apply_repository_patches(ctx, _fail = fail_)
    return struct(calls = ctx.calls, applied = applied), errors

def _test_no_patches_touch_nothing(env):
    ctx, errors = _apply([])
    env.expect.that_bool(ctx.applied).equals(True)
    env.expect.that_collection(ctx.calls).contains_exactly([])
    env.expect.that_collection(errors).contains_exactly([])

def _test_each_patch_applies_without_fuzz(env):
    ctx, errors = _apply(["engine name.patch", "second.patch"], patch_strip = 2)
    env.expect.that_bool(ctx.applied).equals(True)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "watch")]).contains_exactly(
        ["engine name.patch", "second.patch"],
    ).in_order()
    env.expect.that_collection([call.args for call in mocks.calls(ctx, "execute")]).contains_exactly([
        [_PATCH, "-p2", "-F0", "-t", "-N", "-i", "engine name.patch"],
        [_PATCH, "-p2", "-F0", "-t", "-N", "-i", "second.patch"],
    ]).in_order()

def _test_rejected_patch_stops_the_repository(env):
    ctx, errors = _apply(
        ["partial.patch", "later.patch"],
        execute = {_PATCH + " -p1 -F0 -t -N -i partial.patch": {"return_code": 1, "stdout": "1 out of 2 hunks FAILED"}},
    )
    env.expect.that_bool(ctx.applied).equals(False)
    env.expect.that_collection(errors).has_size(1)
    env.expect.that_str(errors[0]).contains("Error applying patch partial.patch (strict matching, fuzz disabled)")
    env.expect.that_str(errors[0]).contains("1 out of 2 hunks FAILED")
    env.expect.that_collection(mocks.calls(ctx, "execute")).has_size(1)

def _test_missing_patch_tool_fails(env):
    ctx, errors = _apply(["engine.patch"], which = {})
    env.expect.that_bool(ctx.applied).equals(False)
    env.expect.that_collection(errors).contains_exactly(
        ["Applying source patches requires the patch command on PATH"],
    )
    env.expect.that_collection(mocks.calls(ctx, "execute")).contains_exactly([])

def patches_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_no_patches_touch_nothing,
            _test_each_patch_applies_without_fuzz,
            _test_rejected_patch_stops_the_repository,
            _test_missing_patch_tool_fails,
        ],
    )
