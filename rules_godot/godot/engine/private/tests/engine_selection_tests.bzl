"""A pack runs and ships only with the engine whose editor exported it."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private:selection.bzl", "require_pack_engine")
load("//godot/private/tests:mocks.bzl", "mocks")

visibility("private")

def _pack(engine):
    return struct(editor_component = struct(engine = engine))

def _check(pack, engine):
    errors, fail_ = mocks.errors()
    require_pack_engine("//game:app", pack, struct(engine = engine, role = "runtime"), _fail = fail_)
    return errors

def _test_the_same_engine_passes(env):
    env.expect.that_collection(_check(_pack("petri"), "petri")).contains_exactly([])
    env.expect.that_collection(_check(_pack(""), "")).contains_exactly([])

def _test_another_engine_fails_naming_the_attribute(env):
    errors = _check(_pack("petri"), "")
    env.expect.that_collection(errors).has_size(1)
    env.expect.that_str(errors[0]).contains(
        "the pack was exported with the editor of the engine petri, but this target's " +
        "runtime is the default engine's; give it engine = \"petri\"",
    )

def _test_a_pack_without_an_export_is_not_compared(env):
    env.expect.that_collection(_check(struct(), "petri")).contains_exactly([])
    env.expect.that_collection(_check(None, "petri")).contains_exactly([])

def engine_selection_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_the_same_engine_passes,
            _test_another_engine_fails_naming_the_attribute,
            _test_a_pack_without_an_export_is_not_compared,
        ],
    )
