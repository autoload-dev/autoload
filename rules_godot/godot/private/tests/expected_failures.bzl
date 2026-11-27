"""An analysis test that targets fail analysis with a given message."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:truth.bzl", "matching")

visibility(["//godot/private/tests/..."])

def failure_test(name, target, message, config_settings = None):
    """
    Declare an analysis test that the analysis of target fails with message.

    Args:
        name: Name of the test.
        target: The target whose analysis must fail, or a list of such targets, each of
            which must.
        message: Glob-style pattern the failure must match; `*` matches anything, such as
            the label of a fixture target inside the message.
        config_settings: Settings of the targets' configuration.
    """
    analysis_test(
        name = name,
        target = target if type(target) == "list" else [target],
        impl = _fails_with_message,
        expect_failure = True,
        attrs = {"message": attr.string()},
        attr_values = {"message": message},
        config_settings = config_settings or {},
    )

def _fails_with_message(env, targets):
    for target in targets:
        env.expect.that_target(target).failures().contains_predicate(
            matching.str_matches(env.ctx.attr.message),
        )
