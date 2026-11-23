"""An analysis test that a target's analysis fails with a given message."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:truth.bzl", "matching")

visibility("private")

def failure_test(name, target, message):
    """
    Declare an analysis test that the analysis of target fails with message.

    Args:
        name: Name of the test.
        target: The target whose analysis must fail.
        message: Glob-style pattern the failure must match; `*` matches anything, such as
            the label of a fixture target inside the message.
    """
    analysis_test(
        name = name,
        target = target,
        impl = _fails_with_message,
        expect_failure = True,
        attrs = {"message": attr.string()},
        attr_values = {"message": message},
    )

def _fails_with_message(env, target):
    env.expect.that_target(target).failures().contains_predicate(
        matching.str_matches(env.ctx.attr.message),
    )
